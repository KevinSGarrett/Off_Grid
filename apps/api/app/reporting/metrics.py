from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import (
    CommercialOutcomeType,
    ContactState,
    CRMObjectType,
    ExceptionStatus,
    QualityFlagState,
    SyncStatus,
)
from app.models import (
    CommercialMotion,
    CommercialOutcome,
    ContactCandidate,
    CRMRecord,
    OpportunityAssessment,
    Project,
    QualityFlag,
    SourceObservation,
    WorkflowException,
)


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    definition: str
    interpretation: str


METRIC_DEFINITIONS: Final[tuple[MetricDefinition, ...]] = (
    MetricDefinition(
        "canonical_projects_resolved",
        "Canonical projects resolved",
        "Distinct non-synthetic Project records after identity resolution.",
        "A project inventory count; not a pursuit recommendation or funnel conversion.",
    ),
    MetricDefinition(
        "source_project_rows",
        "EE Reed source project rows",
        "Retained company-report project-section observations, including repeated rows before canonical resolution.",
        "Source rows are not independent opportunities and must not be added to canonical projects.",
    ),
    MetricDefinition(
        "projects_assessed",
        "Projects assessed",
        "Distinct non-synthetic projects with a current persisted opportunity assessment.",
        "Unassessed projects were not rejected; this is assessment coverage only.",
    ),
    MetricDefinition(
        "authority_verified_contacts",
        "Authority-verified contacts",
        "Current contact candidates whose rental/equipment authority state is AUTHORITY_VERIFIED.",
        "Employment, project association, or role relevance alone do not qualify.",
    ),
    MetricDefinition(
        "crm_leads_previewed",
        "CRM Lead previews",
        "CRM Lead records generated in PREVIEWED state by the dry-run integration.",
        "These are not live Pipedrive Leads and do not indicate outreach authority.",
    ),
    MetricDefinition(
        "open_workflow_exceptions",
        "Open workflow exceptions",
        "WorkflowException records in OPEN or IN_REVIEW state.",
        "Standalone quality warnings are counted separately.",
    ),
    MetricDefinition(
        "quality_warnings_requiring_review",
        "Quality warnings requiring review",
        "QualityFlag records in OPEN or ACKNOWLEDGED state.",
        "A warning describes evidence quality; it is not automatically a workflow exception.",
    ),
    MetricDefinition(
        "progression_blocking_quality_warnings",
        "Progression-blocking warnings",
        "Unresolved quality warnings explicitly marked blocks_progression.",
        "Only this subset is a deterministic progression blocker.",
    ),
    MetricDefinition(
        "recorded_commercial_outcomes",
        "Recorded commercial outcomes",
        "Persisted observed commercial outcomes of any type.",
        "Zero means no outcomes are recorded; it does not prove system failure.",
    ),
)

def definitions_payload() -> dict[str, dict[str, str]]:
    return {item.key: asdict(item) for item in METRIC_DEFINITIONS}


def build_employer_metrics(
    session: Session, *, now: datetime | None = None
) -> dict[str, object]:
    """Compute counts using the definitions exposed alongside the values."""
    current_time = now or datetime.now(UTC)
    cutoff = current_time - timedelta(days=30)
    unresolved_quality = (QualityFlagState.OPEN, QualityFlagState.ACKNOWLEDGED)

    canonical_projects = session.scalar(
        sa.select(sa.func.count()).select_from(Project).where(Project.is_synthetic.is_(False))
    ) or 0
    source_rows = session.scalar(
        sa.select(sa.func.count())
        .select_from(SourceObservation)
        .where(
            SourceObservation.field_name == "company_report.project.section",
            SourceObservation.is_synthetic.is_(False),
        )
    ) or 0
    assessed = session.scalar(
        sa.select(sa.func.count(sa.distinct(OpportunityAssessment.project_id)))
        .join(Project, Project.id == OpportunityAssessment.project_id)
        .where(
            OpportunityAssessment.is_current.is_(True),
            Project.is_synthetic.is_(False),
        )
    ) or 0
    authority_verified = session.scalar(
        sa.select(sa.func.count())
        .select_from(ContactCandidate)
        .where(
            ContactCandidate.state == ContactState.AUTHORITY_VERIFIED,
            ContactCandidate.is_current.is_(True),
        )
    ) or 0
    leads_previewed = session.scalar(
        sa.select(sa.func.count())
        .select_from(CRMRecord)
        .where(
            CRMRecord.object_type == CRMObjectType.LEAD,
            CRMRecord.sync_status == SyncStatus.PREVIEWED,
        )
    ) or 0
    open_exceptions = session.scalar(
        sa.select(sa.func.count())
        .select_from(WorkflowException)
        .where(WorkflowException.status.in_((ExceptionStatus.OPEN, ExceptionStatus.IN_REVIEW)))
    ) or 0
    review_warnings = session.scalar(
        sa.select(sa.func.count())
        .select_from(QualityFlag)
        .where(QualityFlag.state.in_(unresolved_quality))
    ) or 0
    blocking_warnings = session.scalar(
        sa.select(sa.func.count())
        .select_from(QualityFlag)
        .where(
            QualityFlag.state.in_(unresolved_quality),
            QualityFlag.blocks_progression.is_(True),
        )
    ) or 0
    total_outcomes = session.scalar(
        sa.select(sa.func.count())
        .select_from(CommercialOutcome)
        .join(Project, Project.id == CommercialOutcome.project_id)
        .where(Project.is_synthetic.is_(False))
    ) or 0
    demos_30d = session.scalar(
        sa.select(sa.func.count())
        .select_from(CommercialOutcome)
        .join(Project, Project.id == CommercialOutcome.project_id)
        .join(CommercialMotion, CommercialMotion.id == CommercialOutcome.commercial_motion_id)
        .where(
            Project.is_synthetic.is_(False),
            CommercialOutcome.outcome_type == CommercialOutcomeType.DEMO_BOOKED,
            CommercialOutcome.observed_at >= cutoff,
            CommercialOutcome.observed_at <= current_time,
            sa.func.length(sa.func.trim(CommercialOutcome.source)) > 0,
        )
    ) or 0

    diagnostics = {
        "canonical_projects_resolved": int(canonical_projects),
        "source_project_rows": int(source_rows),
        "projects_assessed": int(assessed),
        "authority_verified_contacts": int(authority_verified),
        "crm_leads_previewed": int(leads_previewed),
        "open_workflow_exceptions": int(open_exceptions),
        "quality_warnings_requiring_review": int(review_warnings),
        "progression_blocking_quality_warnings": int(blocking_warnings),
        "recorded_commercial_outcomes": int(total_outcomes),
    }
    return {
        "generated_at": current_time.isoformat(),
        "primary_kpi": {
            "key": "system_sourced_demos_booked_rolling_30_days",
            "name": "System-Sourced Demos Booked — Rolling 30 Days",
            "value": int(demos_30d) if total_outcomes else None,
            "display": str(int(demos_30d)) if total_outcomes else "N/A",
            "status": (
                "AVAILABLE" if total_outcomes else "PRODUCTION_OUTCOME_HISTORY_NOT_CONNECTED"
            ),
            "definition": "Observed DEMO_BOOKED outcomes in the inclusive past-30-day window; future observations are excluded.",
            "interpretation": "N/A means production outcome history is not connected; it is not a zero or a failure result.",
        },
        "diagnostics": diagnostics,
        "definitions": definitions_payload(),
    }
