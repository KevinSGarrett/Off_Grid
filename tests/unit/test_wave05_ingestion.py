from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import ConfidenceState, ScoringTreatment, ValidationState
from app.ingestion.service import ConstructConnectIngestionService
from app.models import (
    Base,
    Organization,
    OrganizationDomain,
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
