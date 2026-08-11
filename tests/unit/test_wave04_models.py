from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import (
    ConfidenceState,
    EvidenceClassification,
    MaskingPolicy,
    PIIClass,
    ProjectState,
    QualityFlagState,
    QualitySeverity,
    ScoringTreatment,
    ValidationState,
    VerificationState,
    ExceptionResolutionAction,
)
from app.models import (
    Base,
    Organization,
    OrganizationAlias,
    OrganizationDomain,
    Project,
    ProjectGroup,
    ProjectOrganization,
    QualityFlag,
    SourceDocument,
    SourceEvidence,
    SourceObservation,
    WorkflowException,
)
from app.persistence.database import build_engine

EXPECTED_TABLES = {
    "source_documents",
    "source_observations",
    "source_evidence",
    "project_groups",
    "projects",
    "project_relationships",
    "project_signals",
    "organizations",
    "organization_aliases",
    "organization_domains",
    "organization_addresses",
    "persons",
    "person_aliases",
    "person_contact_points",
    "project_organizations",
    "project_persons",
    "external_evidence",
    "quality_flags",
    "workflow_exceptions",
    "opportunity_assessments",
    "assessment_factors",
    "product_fit_assessments",
    "contact_candidates",
    "contact_assessments",
    "verification_events",
    "commercial_motions",
    "next_actions",
    "crm_records",
    "crm_sync_attempts",
    "pipeline_runs",
    "pipeline_events",
    "field_history",
    "config_versions",
    "scoring_configs",
    "prompt_runs",
    "ai_claims",
    "ai_claim_evidence",
    "ai_usage",
    "commercial_outcomes",
    "audit_events",
}


def test_wave04_registers_complete_relational_schema() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert len(Base.metadata.tables) == 40


def test_schema_creates_with_foreign_keys_enabled() -> None:
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = sa.inspect(engine)
    assert set(inspector.get_table_names()) == EXPECTED_TABLES
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1


def test_core_domain_is_not_stored_as_giant_json_blobs() -> None:
    relational_truth_tables = {
        "source_documents",
        "source_observations",
        "source_evidence",
        "projects",
        "organizations",
        "persons",
        "project_organizations",
        "project_persons",
        "quality_flags",
        "opportunity_assessments",
        "contact_candidates",
    }
    for table_name in relational_truth_tables:
        table = Base.metadata.tables[table_name]
        assert not any(isinstance(column.type, sa.JSON) for column in table.columns), table_name


def test_stafford_source_truth_and_uncertainty_can_coexist() -> None:
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        group = ProjectGroup(
            canonical_name="Stafford Technology Campus",
            normalized_name="stafford technology campus",
            canonical_key="stafford-technology-campus",
        )
        project = Project(
            project_group_id=group.id,
            canonical_name="Stafford Technology Campus Phases 3 & 4",
            normalized_name="stafford technology campus phases 3 4",
            canonical_key="constructconnect:1007341663",
            source_system="constructconnect",
            external_id="1007341663",
            state=ProjectState.PARSED,
            stage="POST BID - General Contractor Award",
            reported_value=Decimal("7500000000.00"),
            currency_code="USD",
        )
        doc = SourceDocument(
            source_type="constructconnect_pdf",
            source_system="constructconnect",
            external_id="1007341663",
            report_type="project_report",
            original_filename="Stafford-Technology-Campus-Phases-3-4.pdf",
            content_sha256="a" * 64,
            blob_ref="private://stafford.pdf",
            imported_at=now,
        )
        session.add_all([group, project, doc])
        session.flush()
        observation = SourceObservation(
            document_id=doc.id,
            project_id=project.id,
            field_name="reported_project_value",
            value_type="MONEY",
            raw_value="$7,500,000,000.00",
            normalized_decimal=Decimal("7500000000.00"),
            currency_code="USD",
            observation_fingerprint="b" * 64,
            evidence_classification=EvidenceClassification.EXPLICIT,
            confidence_state=ConfidenceState.LOW,
            confidence_reason="Source states phase value is estimated from broader projections.",
            validation_state=ValidationState.REQUIRES_REVIEW,
            scoring_treatment=ScoringTreatment.CAPPED,
        )
        session.add(observation)
        session.flush()
        evidence = SourceEvidence(
            document_id=doc.id,
            observation_id=observation.id,
            page_number=1,
            section_name="Project Description",
            excerpt="The listed square footage and value are estimated based on total project projections.",
            evidence_fingerprint="c" * 64,
            classification=EvidenceClassification.EXPLICIT,
            pii_class=PIIClass.NONE,
            demo_masking_policy=MaskingPolicy.NONE,
        )
        session.add(evidence)
        session.commit()

        saved = session.scalar(sa.select(SourceObservation))
        assert saved is not None
        assert saved.normalized_decimal == Decimal("7500000000.000000")
        assert saved.confidence_state is ConfidenceState.LOW
        assert saved.scoring_treatment is ScoringTreatment.CAPPED
        assert saved.evidence[0].page_number == 1


def test_ee_reed_alias_domain_ambiguity_and_exception_are_representable() -> None:
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        org = Organization(
            canonical_name="EE Reed Construction",
            normalized_name="ee reed construction",
            canonical_key="org:ee-reed-construction",
        )
        project = Project(
            canonical_name="Stafford Technology Campus Phases 3 & 4",
            normalized_name="stafford technology campus phases 3 4",
            canonical_key="constructconnect:1007341663",
            source_system="constructconnect",
            external_id="1007341663",
            state=ProjectState.VALIDATED,
        )
        session.add_all([org, project])
        session.flush()
        session.add_all(
            [
                OrganizationAlias(
                    organization_id=org.id,
                    alias="EE Reed Construction - Houston (HQ)",
                    normalized_alias="ee reed construction houston hq",
                    alias_type="SOURCE_LABEL",
                ),
                OrganizationDomain(
                    organization_id=org.id,
                    domain="eereed.com",
                    normalized_domain="eereed.com",
                    relationship_state=VerificationState.SUPPORTED,
                    is_primary=True,
                ),
                OrganizationDomain(
                    organization_id=org.id,
                    domain="eereedeast.com",
                    normalized_domain="eereedeast.com",
                    relationship_state=VerificationState.UNKNOWN,
                ),
                ProjectOrganization(
                    project_id=project.id,
                    organization_id=org.id,
                    role="GENERAL_CONTRACTOR",
                    verification_state=VerificationState.SUPPORTED,
                ),
            ]
        )
        flag = QualityFlag(
            rule_code="ORGANIZATION_DOMAIN_CONFLICT",
            severity=QualitySeverity.HIGH,
            state=QualityFlagState.OPEN,
            project_id=project.id,
            organization_id=org.id,
            title="Multiple organizational domains require resolution",
            detail="Do not silently merge domains into a single CRM identity.",
            blocks_progression=True,
            first_detected_at=now,
        )
        session.add(flag)
        session.flush()
        session.add(
            WorkflowException(
                quality_flag_id=flag.id,
                project_id=project.id,
                exception_type="AMBIGUOUS_ORGANIZATION",
                recommended_action=ExceptionResolutionAction.VERIFY,
                priority=10,
                summary="Resolve EE Reed organizational relationship before CRM write",
            )
        )
        session.commit()
        assert session.scalar(sa.select(sa.func.count()).select_from(OrganizationDomain)) == 2
        assert session.scalar(sa.select(WorkflowException)).recommended_action.value == "VERIFY"
