from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.domain.states import CommercialOutcomeType, ContactState, ExceptionStatus, SyncStatus, CRMObjectType
from app.models import (
    CommercialOutcome,
    ContactCandidate,
    CRMRecord,
    OpportunityAssessment,
    PipelineRun,
    Project,
    WorkflowException,
)

router = APIRouter(tags=["metrics"])


def _metrics(session: Session) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    projects = session.scalar(sa.select(sa.func.count()).select_from(Project).where(Project.is_synthetic.is_(False))) or 0
    qualified = session.scalar(
        sa.select(sa.func.count(sa.distinct(OpportunityAssessment.project_id))).where(OpportunityAssessment.is_current.is_(True))
    ) or 0
    authority_verified = session.scalar(
        sa.select(sa.func.count()).select_from(ContactCandidate).where(ContactCandidate.state == ContactState.AUTHORITY_VERIFIED, ContactCandidate.is_current.is_(True))
    ) or 0
    leads_previewed = session.scalar(
        sa.select(sa.func.count()).select_from(CRMRecord).where(CRMRecord.object_type == CRMObjectType.LEAD, CRMRecord.sync_status == SyncStatus.PREVIEWED)
    ) or 0
    open_exceptions = session.scalar(
        sa.select(sa.func.count()).select_from(WorkflowException).where(WorkflowException.status.in_([ExceptionStatus.OPEN, ExceptionStatus.IN_REVIEW]))
    ) or 0
    demos_30d = session.scalar(
        sa.select(sa.func.count()).select_from(CommercialOutcome).where(
            CommercialOutcome.outcome_type == CommercialOutcomeType.DEMO_BOOKED,
            CommercialOutcome.observed_at >= cutoff,
        )
    ) or 0
    total_outcomes = session.scalar(sa.select(sa.func.count()).select_from(CommercialOutcome)) or 0
    latest_run = session.scalar(sa.select(PipelineRun).order_by(PipelineRun.started_at.desc(), PipelineRun.created_at.desc()).limit(1))
    return {
        "primary_kpi": {
            "name": "system_sourced_demos_booked_rolling_30_days",
            "value": int(demos_30d) if total_outcomes else None,
            "display": str(int(demos_30d)) if total_outcomes else "N/A",
            "status": "AVAILABLE" if total_outcomes else "PRODUCTION_OUTCOME_HISTORY_NOT_CONNECTED",
        },
        "diagnostics": {
            "projects_ingested": int(projects),
            "projects_qualified": int(qualified),
            "authority_verified_contacts": int(authority_verified),
            "pipedrive_leads_previewed": int(leads_previewed),
            "open_exceptions": int(open_exceptions),
            "commercial_outcomes": int(total_outcomes),
        },
        "latest_pipeline_run": None
        if latest_run is None
        else {"id": str(latest_run.id), "status": latest_run.status.value, "run_type": latest_run.run_type},
    }


@router.get("/metrics")
def get_metrics(session: Session = Depends(get_session)) -> dict[str, object]:
    return _metrics(session)


@router.get("/monday-brief")
def get_monday_brief(session: Session = Depends(get_session)) -> dict[str, object]:
    metrics = _metrics(session)
    top = session.execute(
        sa.select(Project, OpportunityAssessment)
        .join(OpportunityAssessment, OpportunityAssessment.project_id == Project.id)
        .where(OpportunityAssessment.is_current.is_(True), Project.is_synthetic.is_(False))
        .order_by(OpportunityAssessment.commercial_fit_score.desc(), OpportunityAssessment.data_confidence_score.desc())
        .limit(1)
    ).first()
    attention = session.scalars(
        sa.select(WorkflowException)
        .where(WorkflowException.status.in_([ExceptionStatus.OPEN, ExceptionStatus.IN_REVIEW]))
        .order_by(WorkflowException.priority.desc())
        .limit(5)
    ).all()
    return {
        "title": "Off Grid Commercial Intelligence — Monday Brief",
        "primary_kpi": metrics["primary_kpi"],
        "top_opportunity": None
        if top is None
        else {
            "project_id": str(top[0].id),
            "external_id": top[0].external_id,
            "name": top[0].canonical_name,
            "commercial_fit": str(top[1].commercial_fit_score),
            "data_confidence": str(top[1].data_confidence_score),
            "disposition": top[1].disposition,
        },
        "pipeline": metrics["diagnostics"],
        "attention_required": [
            {"id": str(row.id), "priority": row.priority, "summary": row.summary, "status": row.status.value}
            for row in attention
        ],
    }
