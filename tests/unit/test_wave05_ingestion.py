from __future__ import annotations

from pathlib import Path

import fitz
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import ConfidenceState, ScoringTreatment, ValidationState
from app.ingestion.service import ConstructConnectIngestionService
from app.models import (
    Base,
    FieldHistory,
    Organization,
    OrganizationDomain,
    PipelineEvent,
    PipelineRun,
    Project,
    QualityFlag,
    SourceDocument,
    SourceObservation,
)
from app.persistence.database import build_engine

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


def _session() -> Session:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _write_stafford_like_pdf(path: Path, *, stage: str) -> None:
    content = f"""Example Stafford Technology Campus
Category:
Offices
Project ID #:
SYNTH-PROJECT-001
Staff Estimate Value
$1,000,000
County:
Stafford
Stage:
{stage}
Last Update:
8/11/2026
Project Description
Scope
Site work and new construction
Completed plans are available
Notes
Synthetic material-change fixture
Project Events
Design Team
Report Date: 8/11/2026 8:00 AM"""
    document = fitz.open()
    try:
        page = document.new_page(width=612, height=792)
        remaining = page.insert_textbox(
            fitz.Rect(40, 40, 570, 750), content, fontsize=9, fontname="helv"
        )
        assert remaining >= 0
        document.save(path)
    finally:
        document.close()


def test_real_sources_persist_into_wave04_model_with_required_quality_flags() -> None:
    with _session() as session:
        svc = ConstructConnectIngestionService(session)
        stafford_result = svc.ingest(STAFFORD)
        company_result = svc.ingest(EE_REED)
        assert stafford_result.created_document
        assert company_result.reconciliation_passed
        assert company_result.parsed_project_rows == 167
        assert company_result.parsed_contacts == 32

        project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
        assert project is not None
        value_obs = session.scalar(
            sa.select(SourceObservation).where(
                SourceObservation.project_id == project.id,
                SourceObservation.field_name == "project.reported_value",
            )
        )
        assert value_obs is not None
        assert value_obs.confidence_state is ConfidenceState.LOW
        assert value_obs.validation_state is ValidationState.REQUIRES_REVIEW
        assert value_obs.scoring_treatment is ScoringTreatment.CAPPED
        project_flags = {f.rule_code for f in session.scalars(sa.select(QualityFlag).where(QualityFlag.project_id == project.id))}
        assert {"PROJECT_VALUE_UNCERTAINTY", "FUTURE_ACTUAL_DATE", "MISSING_PROJECT_GC_CONTACT"} <= project_flags

        org = session.scalar(sa.select(Organization).where(Organization.canonical_key == "constructconnect:company:1000647848"))
        assert org is not None
        domains = {d.normalized_domain for d in session.scalars(sa.select(OrganizationDomain).where(OrganizationDomain.organization_id == org.id))}
        assert {"eereed.com", "eereedeast.com", "zapalacreed.com"} <= domains
        org_flags = {f.rule_code for f in session.scalars(sa.select(QualityFlag).where(QualityFlag.organization_id == org.id))}
        assert {"GENERIC_CONTACT_EMAIL", "ORGANIZATION_DOMAIN_CONFLICT", "POSSIBLE_DUPLICATE_CONTACT"} <= org_flags


def test_reprocessing_identical_stafford_pdf_is_idempotent() -> None:
    with _session() as session:
        svc = ConstructConnectIngestionService(session)
        first = svc.ingest(STAFFORD)
        document_count = session.scalar(sa.select(sa.func.count()).select_from(SourceDocument))
        observation_count = session.scalar(sa.select(sa.func.count()).select_from(SourceObservation))
        flag_count = session.scalar(sa.select(sa.func.count()).select_from(QualityFlag))
        second = svc.ingest(STAFFORD)
        assert first.created_document is True
        assert second.duplicate_prevented is True
        assert session.scalar(sa.select(sa.func.count()).select_from(SourceDocument)) == document_count == 1
        assert session.scalar(sa.select(sa.func.count()).select_from(SourceObservation)) == observation_count
        assert session.scalar(sa.select(sa.func.count()).select_from(QualityFlag)) == flag_count
        assert session.scalar(sa.select(sa.func.count()).select_from(Project).where(Project.external_id == "1007341663")) == 1
        runs = session.scalars(sa.select(PipelineRun).order_by(PipelineRun.created_at)).all()
        assert len(runs) == 2
        assert runs[-1].duplicate_count == 1


def test_later_material_project_change_creates_history_and_pipeline_event(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "stafford-initial.pdf"
    changed = tmp_path / "stafford-changed.pdf"
    original_stage = "POST BID - General Contractor Award"
    changed_stage = "BIDDING - General Contractor Selection"
    _write_stafford_like_pdf(initial, stage=original_stage)
    _write_stafford_like_pdf(changed, stage=changed_stage)

    with _session() as session:
        service = ConstructConnectIngestionService(session)
        first = service.ingest(initial)
        assert session.scalar(sa.select(sa.func.count()).select_from(FieldHistory)) == 0

        second = service.ingest(changed)
        project = session.get(Project, first.canonical_entity_id)
        assert project is not None
        assert second.canonical_entity_id == project.id
        assert project.stage == changed_stage

        history = session.scalar(sa.select(FieldHistory))
        assert history is not None
        assert history.pipeline_run_id == second.pipeline_run_id
        assert history.source_document_id == second.source_document_id
        assert history.entity_type == "Project"
        assert history.entity_id == str(project.id)
        assert history.field_name == "project.stage"
        assert history.previous_value == original_stage
        assert history.new_value == changed_stage
        assert history.change_type == "MATERIAL_SOURCE_CHANGE"
        assert history.commercial_impact == "HIGH"
        assert history.detected_at is not None

        change_event = session.scalar(
            sa.select(PipelineEvent).where(
                PipelineEvent.pipeline_run_id == second.pipeline_run_id,
                PipelineEvent.event_type == "MATERIAL_FIELD_CHANGED",
            )
        )
        assert change_event is not None
        assert change_event.stage == "CHANGE_DETECTION"
        assert change_event.entity_id == str(project.id)
        assert change_event.message == "project.stage"
        assert change_event.safe_metadata == {
            "field_name": "project.stage",
            "change_type": "MATERIAL_SOURCE_CHANGE",
            "commercial_impact": "HIGH",
            "source_document_id": str(second.source_document_id),
        }
        assert session.get(PipelineRun, second.pipeline_run_id).updated_count == 1

        observations = session.scalars(
            sa.select(SourceObservation).where(
                SourceObservation.project_id == project.id,
                SourceObservation.field_name == "project.stage",
            )
        ).all()
        assert {observation.normalized_text for observation in observations} == {
            original_stage,
            changed_stage,
        }
        assert {observation.document_id for observation in observations} == {
            first.source_document_id,
            second.source_document_id,
        }

        history_count = session.scalar(sa.select(sa.func.count()).select_from(FieldHistory))
        duplicate = service.ingest(changed)
        assert duplicate.duplicate_prevented is True
        assert session.scalar(sa.select(sa.func.count()).select_from(FieldHistory)) == history_count == 1
        assert (
            session.scalar(
                sa.select(sa.func.count())
                .select_from(PipelineEvent)
                .where(
                    PipelineEvent.pipeline_run_id == duplicate.pipeline_run_id,
                    PipelineEvent.event_type == "MATERIAL_FIELD_CHANGED",
                )
            )
            == 0
        )


def test_exact_stafford_reuse_is_order_independent_across_supplied_reports() -> None:
    with _session() as session:
        svc = ConstructConnectIngestionService(session)
        svc.ingest(EE_REED)
        before = session.scalar(sa.select(sa.func.count()).select_from(Project))
        svc.ingest(STAFFORD)
        # The standalone report upgrades the exact name+geography company-row project rather than adding another Stafford.
        after = session.scalar(sa.select(sa.func.count()).select_from(Project))
        assert after == before
        assert session.scalar(sa.select(sa.func.count()).select_from(Project).where(Project.external_id == "1007341663")) == 1
