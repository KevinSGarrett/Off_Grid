from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import VerificationState
from app.ingestion.service import ConstructConnectIngestionService
from app.models import Base, ConfigVersion, Organization, OrganizationAlias, OrganizationDomain, Project, ProjectGroup, ProjectPerson, ProjectRelationship
from app.persistence.database import build_engine
from app.resolution.organizations import OrganizationResolutionService
from app.resolution.projects import compare_projects, extract_phase_descriptor
from app.resolution.service import Wave07ResolutionService
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


def _session() -> Session:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(session: Session):
    svc = ConstructConnectIngestionService(session)
    svc.ingest(STAFFORD)
    svc.ingest(EE_REED)
    stafford = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    QualificationService(session).evaluate(stafford.id, persist=True)
    return stafford, Wave07ResolutionService(session).run()


def test_stafford_phase_descriptor_and_cluster_are_structured_and_not_blindly_summed() -> None:
    d = extract_phase_descriptor("Stafford Technology Campus Phases 3 & 4")
    assert d.base_name == "Stafford Technology Campus"
    assert (d.phase_start_number, d.phase_end_number) == (3, 4)
    with _session() as session:
        _, result = _seed(session)
        cluster = result.stafford_cluster
        assert cluster.member_names == (
            "Stafford Technology Campus Phases 1 & 2",
            "Stafford Technology Campus Phases 3 & 4",
        )
        assert cluster.naive_reported_value_sum == 10_000_000_000
        assert cluster.value_aggregation_allowed is False
        assert session.scalar(sa.select(sa.func.count()).select_from(ProjectGroup)) == 1
        rel = session.scalar(sa.select(ProjectRelationship))
        assert rel.verification_state is VerificationState.SUPPORTED
        assert rel.confidence_score >= 0.9
        assert rel.source_observation_id is not None


def test_ee_reed_source_label_becomes_alias_while_division_domains_remain_unresolved() -> None:
    with _session() as session:
        _, result = _seed(session)
        org = session.get(Organization, result.ee_reed_organization_id)
        assert org.canonical_name == "EE Reed Construction"
        aliases = {x.alias for x in session.scalars(sa.select(OrganizationAlias).where(OrganizationAlias.organization_id == org.id)).all()}
        assert "EE Reed Construction - Houston (HQ)" in aliases
        domains = {x.normalized_domain: x for x in session.scalars(sa.select(OrganizationDomain).where(OrganizationDomain.organization_id == org.id)).all()}
        assert domains["eereed.com"].relationship_state is VerificationState.SUPPORTED
        assert domains["eereedeast.com"].relationship_state is VerificationState.UNKNOWN
        assert domains["zapalacreed.com"].relationship_state is VerificationState.UNKNOWN
        assert result.organization_match.review_required is True
        assert result.account_intelligence.entity_resolution_state == "REVIEW_DIVISION_RELATIONSHIP"


def test_entity_matching_is_deterministic_first_and_fuzzy_only_recommends_review() -> None:
    with _session() as session:
        _, result = _seed(session)
        org = session.get(Organization, result.ee_reed_organization_id)
        other = Organization(canonical_name="E.E. Reed Construction East", normalized_name="e e reed construction east", canonical_key="test:east")
        session.add(other); session.flush()
        decision = OrganizationResolutionService(session).compare(org, other)
        assert decision.decision in {"REVIEW", "NO_MATCH"}
        assert decision.deterministic is False
        assert decision.decision != "AUTO_MATCH"


def test_contact_duplicate_clusters_and_recurrence_do_not_imply_authority() -> None:
    with _session() as session:
        _, result = _seed(session)
        pairs = {(x.canonical_name, x.duplicate_name, x.match_method) for x in result.duplicate_people}
        assert any(a == "Curtis Rakosi" and b == "Curits Rakosi" and "FUZZY" in method for a, b, method in pairs)
        assert sum(1 for x in result.duplicate_people if x.canonical_name == "Dan Delforge") == 2
        recurrence = {x.person_name: x for x in result.account_intelligence.recurring_contacts}
        assert recurrence["Dan Delforge"].unique_project_count == 5
        assert recurrence["Dan Delforge"].rental_authority_implied is False
        assert session.scalar(sa.select(sa.func.count()).select_from(ProjectPerson)) == 17


def test_account_intelligence_reconciles_source_rows_but_reports_unique_projects_and_freshness() -> None:
    with _session() as session:
        _, result = _seed(session)
        acct = result.account_intelligence
        assert acct.source_section_counts == {"BIDDING_ROLE": 74, "PLANNING": 6, "POST_BID": 87}
        assert acct.source_project_rows == 167
        assert acct.unique_projects == 165
        bands = {x.band: x for x in acct.activity_bands}
        assert bands["CURRENT_SOURCE_SECTION"].source_row_count == 6
        assert bands["HISTORICAL_DATED"].source_row_count > bands["RECENT_DATED"].source_row_count
        assert acct.strategic_signal_band == "STRONG_REPEAT_ACTIVITY"
        assert acct.account_recommendation == "INVESTIGATE_AS_STRATEGIC_ACCOUNT"


def test_resolution_config_is_versioned() -> None:
    with _session() as session:
        _seed(session)
        row = session.scalar(sa.select(ConfigVersion).where(ConfigVersion.config_kind == "entity_resolution"))
        assert row.version == "entity-resolution-1.0"
        assert row.is_active is True
