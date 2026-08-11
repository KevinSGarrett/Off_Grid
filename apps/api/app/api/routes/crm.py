from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_policy, get_session
from app.api.serialization import jsonable
from app.crm.service import Wave10IntegrationService
from app.models import Project

router = APIRouter(tags=["crm"])


def _run(session: Session, project_id: UUID):
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(project_id)})
    try:
        return Wave10IntegrationService(session).run(project.external_id or "")
    except Exception as exc:
        raise HTTPException(status_code=409, detail={"code": "CRM_PREREQUISITES_NOT_READY", "message": str(exc)}) from exc


@router.get("/projects/{project_id}/crm-readiness")
def get_crm_readiness(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    result = _run(session, project_id)
    return jsonable(result.readiness)


@router.get("/projects/{project_id}/crm-preview")
def get_crm_preview(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    result = _run(session, project_id)
    return {
        "readiness": jsonable(result.readiness),
        "pipedrive": jsonable(result.pipedrive),
        "sheets": jsonable(result.sheets),
        "forms": jsonable(result.forms),
        "trello": jsonable(result.trello),
        "external_writes_executed": result.external_writes_executed,
    }


@router.post("/projects/{project_id}/crm-sync")
def sync_crm_command(
    project_id: UUID,
    session: Session = Depends(get_session),
    policy=Depends(get_runtime_policy),
) -> dict[str, object]:
    """Fail-closed command envelope.

    Wave 12 exposes the command boundary but does not introduce a new live-write implementation.
    The owner-wave integration service still produces deterministic preview/blocked requests only.
    """
    result = _run(session, project_id)
    eligible = [request for request in result.pipedrive.requests if request.status.value == "PREVIEWED"]
    return {
        "command_status": "BLOCKED" if policy.demo_mode else "PREVIEWED",
        "reason": "DEMO_MODE blocks external writes" if policy.demo_mode else "Wave 12 exposes the validated dry-run contract; live Pipedrive execution remains disabled without an explicitly authorized live adapter.",
        "eligible_preview_count": len(eligible),
        "requests": jsonable(result.pipedrive.requests),
        "external_write_performed": False,
    }
