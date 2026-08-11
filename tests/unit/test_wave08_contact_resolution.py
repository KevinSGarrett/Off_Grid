from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.contact_resolution.service import Wave08ContactResolutionService
from app.domain.states import ContactState, VerificationState
from app.ingestion.service import ConstructConnectIngestionService
from app.models import (
    Base,
    ContactAssessment,
    ContactCandidate,
    ExternalEvidence,
    Organization,
    OrganizationDomain,
    Project,
    ProjectOrganization,
    QualityFlag,
    VerificationEvent,
)
from app.persistence.database import build_engine
from app.resolution.service import Wave07ResolutionService
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"
EXPECTED = json.loads((ROOT / "tests/golden/stafford_wave08_expected.json").read_text())


def _session() -> Session:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _build_through_wave08(session: Session):
    ingest = ConstructConnectIngestionService(session)
    ingest.ingest(STAFFORD)
    ingest.ingest(EE_REED)
    stafford = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    QualificationService(session).evaluate(stafford.id, persist=True)
    Wave07ResolutionService(session).run()
    result = Wave08ContactResolutionService(session).run()
    return stafford, result


def test_public_research_ranks_real_candidate_without_inventing_rental_authority() -> None:
    with _session() as session:
        _, result = _build_through_wave08(session)
        assert result.contact_resolution_version == EXPECTED["contact_resolution_version"]
        assert result.persona_version == EXPECTED["persona_version"]
        assert result.source_precedence_version == EXPECTED["source_precedence_version"]
        assert {row.person_name for row in result.candidates} == set(EXPECTED["required_candidates"])
        top = result.candidates[0]
        assert top.person_name == EXPECTED["top_candidate"]
        assert top.state.value == EXPECTED["top_candidate_expected_state"]
        assert top.project_association_state.value == EXPECTED["top_candidate_project_association"]
        assert top.rental_authority_state.value == EXPECTED["top_candidate_rental_authority"]
        assert result.authority_verified_count == EXPECTED["authority_verified_count"] == 0
        assert all(row.state is not ContactState.AUTHORITY_VERIFIED for row in result.candidates)


def test_dimension_states_are_separate_and_state_machine_does_not_skip_project_association() -> None:
    with _session() as session:
        _, result = _build_through_wave08(session)
        rows = {row.person_name: row for row in result.candidates}
        doug = rows["Doug Meadows"]
        alex = rows["Alex Gutenson"]
        assert doug.employment_state is VerificationState.VERIFIED
        assert doug.project_association_state is VerificationState.VERIFIED
        assert doug.role_relevance_state is VerificationState.VERIFIED
        assert doug.rental_authority_state is VerificationState.UNKNOWN
        assert doug.state is ContactState.ROLE_RELEVANT
        assert alex.employment_state is VerificationState.VERIFIED
        assert alex.role_relevance_state is VerificationState.VERIFIED
        assert alex.project_association_state is VerificationState.UNKNOWN
        assert alex.state is ContactState.EMPLOYMENT_VERIFIED


def test_east_coast_public_entity_is_distinct_and_source_houston_relationship_is_preserved() -> None:
    with _session() as session:
        stafford, result = _build_through_wave08(session)
        public_org = session.get(Organization, result.east_coast_organization_id)
        source_org = session.scalar(
            sa.select(Organization).where(Organization.canonical_key == "constructconnect:company:1000647848")
        )
        assert public_org.canonical_key == EXPECTED["east_coast_canonical_key"]
        assert public_org.id != source_org.id
        public_domain = session.scalar(
            sa.select(OrganizationDomain).where(
                OrganizationDomain.organization_id == public_org.id,
                OrganizationDomain.normalized_domain == "eereedeast.com",
            )
        )
        assert public_domain.relationship_state is VerificationState.VERIFIED
        source_gc = session.scalar(
            sa.select(ProjectOrganization).where(
                ProjectOrganization.project_id == stafford.id,
                ProjectOrganization.role == "General Contractor",
            )
        )
        assert source_gc is not None
        assert source_gc.organization_id == source_org.id


def test_external_evidence_and_verification_events_are_idempotent() -> None:
    with _session() as session:
        _, first = _build_through_wave08(session)
        evidence_first = session.scalar(sa.select(sa.func.count()).select_from(ExternalEvidence))
        events_first = session.scalar(sa.select(sa.func.count()).select_from(VerificationEvent))
        candidates_first = session.scalar(sa.select(sa.func.count()).select_from(ContactCandidate))
        second = Wave08ContactResolutionService(session).run()
        assert session.scalar(sa.select(sa.func.count()).select_from(ExternalEvidence)) == evidence_first
        assert session.scalar(sa.select(sa.func.count()).select_from(VerificationEvent)) == events_first
        assert session.scalar(sa.select(sa.func.count()).select_from(ContactCandidate)) == candidates_first
        assert second.candidates[0].person_name == first.candidates[0].person_name
        assert session.scalar(sa.select(sa.func.count()).select_from(ContactAssessment).where(ContactAssessment.is_current.is_(True))) == len(first.candidates)


def test_role_title_variance_is_visible_but_does_not_invent_authority() -> None:
    with _session() as session:
        _, result = _build_through_wave08(session)
        top = result.candidates[0]
        flags = session.scalars(
            sa.select(QualityFlag).where(QualityFlag.person_id == top.person_id)
        ).all()
        assert any(flag.rule_code == "PUBLIC_ROLE_TITLE_VARIANCE" for flag in flags)
        assert top.rental_authority_state is VerificationState.UNKNOWN


def test_apollo_workflow_is_search_rank_then_selected_enrichment_preview_only() -> None:
    with _session() as session:
        _, result = _build_through_wave08(session)
        assert result.apollo_preview.mode == "preview"
        assert result.apollo_preview.search_endpoint == EXPECTED["apollo_search_endpoint"]
        assert result.apollo_preview.enrichment_endpoint == EXPECTED["apollo_enrichment_endpoint"]
        assert len(result.apollo_preview.enrichment_candidate_ids) == 3
        assert result.apollo_preview.enrichment_candidate_ids[0] == result.candidates[0].candidate_id
        assert any("No Apollo network call" in note for note in result.apollo_preview.notes)


def test_direct_verification_path_records_human_confirmation_without_performing_outreach() -> None:
    from app.contact_resolution.verification import ContactVerificationService

    with _session() as session:
        _, result = _build_through_wave08(session)
        doug = result.candidates[0]
        service = ContactVerificationService(session)
        event = service.record(
            candidate_id=doug.candidate_id,
            dimension="rental_authority",
            verification_type="PHONE_CONFIRMATION",
            outcome=VerificationState.VERIFIED,
            verified_by="authorized_human_reviewer",
            note="Test-only recorded confirmation; no phone call is performed by the application.",
        )
        candidate = session.get(ContactCandidate, doug.candidate_id)
        assessment = session.scalar(
            sa.select(ContactAssessment).where(
                ContactAssessment.candidate_id == doug.candidate_id,
                ContactAssessment.is_current.is_(True),
            )
        )
        assert event.verification_type == "PHONE_CONFIRMATION"
        assert event.outcome is VerificationState.VERIFIED
        assert assessment.rental_authority_state is VerificationState.VERIFIED
        assert candidate.state is ContactState.AUTHORITY_VERIFIED


def test_rental_authority_rejects_weak_manual_research_as_verified_authority() -> None:
    from app.contact_resolution.verification import ContactVerificationService

    with _session() as session:
        _, result = _build_through_wave08(session)
        doug = result.candidates[0]
        service = ContactVerificationService(session)
        import pytest

        with pytest.raises(ValueError, match="Rental authority may be VERIFIED only"):
            service.record(
                candidate_id=doug.candidate_id,
                dimension="rental_authority",
                verification_type="MANUAL_RESEARCH",
                outcome=VerificationState.VERIFIED,
                verified_by="researcher",
                note="A title or generic web profile is not enough to prove equipment-rental authority.",
            )
