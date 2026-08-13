from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.commercial_workflow.service import Wave09CommercialWorkflowService
from app.models import CommercialMotion, NextAction, Project

router = APIRouter(tags=["commercial-workflow"])


def _ensure_project(session: Session, project_id: UUID) -> None:
    if session.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(project_id)})


@router.get("/projects/{project_id}/actions")
def get_actions(
    project_id: UUID,
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI dependency injection
) -> dict[str, object]:
    _ensure_project(session, project_id)
    rows = session.scalars(
        sa.select(NextAction)
        .where(NextAction.project_id == project_id)
        .order_by(NextAction.priority.asc(), NextAction.created_at.asc())
    ).all()
    by_id = {row.id: row.action_type for row in rows}
    kit = Wave09CommercialWorkflowService(session).current_first_call_kit(project_id)
    return {
        "project_id": str(project_id),
        "ordering": "DEPENDENCY_EXECUTION_ASC",
        "items": [
            {
                "id": str(row.id),
                "commercial_motion_id": str(row.commercial_motion_id) if row.commercial_motion_id else None,
                "dependency_action_id": str(row.dependency_action_id) if row.dependency_action_id else None,
                "dependency_action_type": by_id.get(row.dependency_action_id),
                "action_type": row.action_type,
                "status": row.status.value,
                "priority": row.priority,
                "owner": row.owner,
                "reason": row.reason,
                "due_at": row.due_at.isoformat() if row.due_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in rows
        ],
        "first_call_kit": {
            "version": kit.version,
            "target_candidate_id": str(kit.target_candidate_id) if kit.target_candidate_id else None,
            "target_person_name": kit.target_person_name,
            "target_status": kit.target_status,
            "objective": kit.objective,
            "questions": list(kit.questions),
            "after_call_capture": list(kit.after_call_capture),
            "safeguards": list(kit.safeguards),
        },
    }


@router.get("/projects/{project_id}/commercial-motions")
def get_commercial_motions(
    project_id: UUID,
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI dependency injection
) -> dict[str, object]:
    _ensure_project(session, project_id)
    rows = session.scalars(sa.select(CommercialMotion).where(CommercialMotion.project_id == project_id).order_by(CommercialMotion.motion_type)).all()
    return {
        "project_id": str(project_id),
        "items": [
            {
                "id": str(row.id),
                "motion_type": row.motion_type.value,
                "organization_id": str(row.organization_id) if row.organization_id else None,
                "status": row.status.value,
                "demand_strength": row.demand_strength,
                "confidence_state": row.confidence_state.value,
                "owner": row.owner,
                "summary": row.summary,
            }
            for row in rows
        ],
    }
