from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_internal_mutation_allowed
from app.api.serialization import jsonable
from app.models import PipelineEvent, PipelineRun, Project
from app.pipeline.orchestrator import CommercialPipelineOrchestrator

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline/runs")
def list_pipeline_runs(
    limit: int = Query(50, ge=1, le=250),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    rows = session.scalars(sa.select(PipelineRun).order_by(PipelineRun.started_at.desc(), PipelineRun.created_at.desc()).limit(limit)).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "run_type": row.run_type,
                "mode": row.mode,
                "status": row.status.value,
                "correlation_id": row.correlation_id,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "source_document_count": row.source_document_count,
                "created_count": row.created_count,
                "updated_count": row.updated_count,
                "duplicate_count": row.duplicate_count,
                "exception_count": row.exception_count,
                "error_summary": row.error_summary,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.get("/pipeline/runs/{run_id}")
def get_pipeline_run(run_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.get(PipelineRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "PIPELINE_RUN_NOT_FOUND", "run_id": str(run_id)})
    events = session.scalars(sa.select(PipelineEvent).where(PipelineEvent.pipeline_run_id == run_id).order_by(PipelineEvent.sequence_number)).all()
    return {
        "run": {
            "id": str(row.id),
            "run_type": row.run_type,
            "mode": row.mode,
            "status": row.status.value,
            "correlation_id": row.correlation_id,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "source_document_count": row.source_document_count,
            "created_count": row.created_count,
            "updated_count": row.updated_count,
            "duplicate_count": row.duplicate_count,
            "exception_count": row.exception_count,
            "error_summary": row.error_summary,
        },
        "events": [
            {
                "sequence_number": event.sequence_number,
                "event_type": event.event_type,
                "stage": event.stage,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "message": event.message,
                "safe_metadata": event.safe_metadata,
                "occurred_at": event.occurred_at.isoformat(),
            }
            for event in events
        ],
    }


@router.post("/projects/{project_id}/pipeline/refresh")
def refresh_project_pipeline(
    project_id: UUID,
    _policy=Depends(require_internal_mutation_allowed),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if session.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(project_id)})
    try:
        stages = CommercialPipelineOrchestrator(session).refresh_project(project_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"code": "PIPELINE_REFRESH_FAILED", "message": str(exc)}) from exc
    return {"project_id": str(project_id), "stages": jsonable(stages)}
