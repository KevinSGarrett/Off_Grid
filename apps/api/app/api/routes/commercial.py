from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.commercial_workflow.service import Wave09CommercialWorkflowService
from app.models import CommercialMotion, NextAction, Project

router = APIRouter(tags=["commercial-workflow"])


def _step(label: str, state: str, source: str) -> dict[str, str]:
    return {"label": label, "state": state, "source": source}


def _dependency_map(
    motion: CommercialMotion, actions: dict[str, NextAction]
) -> list[dict[str, str]]:
    def action_step(action_type: str, label: str) -> dict[str, str]:
        action = actions.get(action_type)
        return _step(
            label,
            action.status.value if action else "UNRESOLVED",
            f"next_action:{action_type}",
        )

    if motion.motion_type.value == "CONTRACTOR":
        responsibility = actions.get("VERIFY_SITE_EQUIPMENT_RESPONSIBILITY")
        return [
            _step("Project identified", "IDENTIFIED", "canonical_project"),
            _step(
                "GC relationship identified",
                "IDENTIFIED" if motion.organization_id else "UNRESOLVED",
                "project_organization",
            ),
            _step(
                "Project-associated contact",
                "IDENTIFIED"
                if responsibility and responsibility.external_evidence_id
                else "UNRESOLVED",
                "project_contact_evidence",
            ),
            action_step(
                "VERIFY_SITE_EQUIPMENT_RESPONSIBILITY", "Equipment / rental authority"
            ),
            action_step(
                "VALIDATE_TEMP_LIGHTING_POWER_NEED", "Current lighting / power need"
            ),
            action_step("PREPARE_SITE_DEMO_PATH", "Demo path"),
        ]
    return [
        action_step("VALIDATE_TEMP_LIGHTING_POWER_NEED", "Validated contractor need"),
        action_step("IDENTIFY_INCUMBENT_RENTAL_PROVIDER", "Rental provider"),
        action_step("RESOLVE_RENTAL_BRANCH_FLEET_BUYER", "Serving branch / fleet buyer"),
        action_step("VALIDATE_FLEET_OPPORTUNITY", "Fleet / demo opportunity"),
    ]


def _demand_display(motion: CommercialMotion) -> str:
    if motion.motion_type.value == "RENTAL_HOUSE":
        return "Rental-house motion depends on validated contractor demand."
    return "Current site lighting and mobile-power demand is not yet verified."


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
    action_rows = session.scalars(
        sa.select(NextAction)
        .where(NextAction.project_id == project_id)
        .order_by(NextAction.priority.asc())
    ).all()
    actions = {row.action_type: row for row in action_rows}
    return {
        "project_id": str(project_id),
        "items": [
            {
                "id": str(row.id),
                "motion_type": row.motion_type.value,
                "organization_id": str(row.organization_id) if row.organization_id else None,
                "status": row.status.value,
                "demand_strength": row.demand_strength,
                "demand_display": _demand_display(row),
                "confidence_state": row.confidence_state.value,
                "owner": row.owner,
                "summary": row.summary,
                "dependency_map": _dependency_map(row, actions),
            }
            for row in rows
        ],
    }
