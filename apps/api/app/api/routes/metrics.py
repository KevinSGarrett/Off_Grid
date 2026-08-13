from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.domain.states import ExceptionStatus
from app.models import OpportunityAssessment, PipelineRun, Project, WorkflowException
from app.reporting.metrics import build_employer_metrics

router = APIRouter(tags=["metrics"])


def _metrics(session: Session) -> dict[str, object]:
    metrics = build_employer_metrics(session)
    latest_run = session.scalar(sa.select(PipelineRun).order_by(PipelineRun.started_at.desc(), PipelineRun.created_at.desc()).limit(1))
    metrics["latest_pipeline_run"] = (
        None
        if latest_run is None
        else {
            "id": str(latest_run.id),
            "status": latest_run.status.value,
            "run_type": latest_run.run_type,
        }
    )
    return metrics


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
        "metric_definitions": metrics["definitions"],
        "pipeline_semantics": "Current demo snapshot; these diagnostics are not production funnel conversion data.",
        "attention_required": [
            {
                "id": str(row.id),
                "item_type": "WORKFLOW_EXCEPTION",
                "priority": row.priority,
                "summary": row.summary,
                "detail": row.detail,
                "status": row.status.value,
                "recommended_action": row.recommended_action.value,
            }
            for row in attention
        ],
    }
