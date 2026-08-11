from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_internal_mutation_allowed
from app.domain.states import ExceptionResolutionAction, ExceptionStatus, QualityFlagState
from app.models import QualityFlag, WorkflowException

router = APIRouter(tags=["exceptions"])


class ExceptionResolutionRequest(BaseModel):
    action: ExceptionResolutionAction
    note: str = Field(min_length=1, max_length=4000)
    owner: str | None = Field(default=None, max_length=160)


@router.get("/exceptions")
def list_exceptions(
    status_filter: ExceptionStatus | None = Query(default=None, alias="status"),
    project_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    stmt = sa.select(WorkflowException).order_by(WorkflowException.priority.desc(), WorkflowException.created_at).limit(limit)
    if status_filter is not None:
        stmt = stmt.where(WorkflowException.status == status_filter)
    if project_id is not None:
        stmt = stmt.where(WorkflowException.project_id == project_id)
    rows = session.scalars(stmt).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "project_id": str(row.project_id) if row.project_id else None,
                "quality_flag_id": str(row.quality_flag_id) if row.quality_flag_id else None,
                "exception_type": row.exception_type,
                "status": row.status.value,
                "recommended_action": row.recommended_action.value,
                "priority": row.priority,
                "summary": row.summary,
                "detail": row.detail,
                "owner": row.owner,
                "resolution_note": row.resolution_note,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/exceptions/{exception_id}/resolution")
def resolve_exception(
    exception_id: UUID,
    payload: ExceptionResolutionRequest,
    _policy=Depends(require_internal_mutation_allowed),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    row = session.get(WorkflowException, exception_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "EXCEPTION_NOT_FOUND", "exception_id": str(exception_id)})
    now = datetime.now(timezone.utc)
    row.owner = payload.owner or row.owner
    row.resolution_note = payload.note
    if payload.action in {ExceptionResolutionAction.IGNORE, ExceptionResolutionAction.CORRECT, ExceptionResolutionAction.VERIFY}:
        row.status = ExceptionStatus.RESOLVED
        row.resolved_at = now
        if row.quality_flag_id:
            flag = session.get(QualityFlag, row.quality_flag_id)
            if flag is not None:
                flag.state = QualityFlagState.RESOLVED if payload.action is not ExceptionResolutionAction.IGNORE else QualityFlagState.WAIVED
                flag.resolved_at = now
    elif payload.action in {ExceptionResolutionAction.RETRY, ExceptionResolutionAction.ESCALATE}:
        row.status = ExceptionStatus.IN_REVIEW
    else:
        row.status = ExceptionStatus.OPEN
    session.commit()
    return {"id": str(row.id), "status": row.status.value, "action": payload.action.value, "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None}
