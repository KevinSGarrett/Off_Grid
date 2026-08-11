from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_internal_mutation_allowed
from app.commercial_workflow.outcomes import CommercialOutcomeService
from app.domain.states import CommercialOutcomeType, LossReason
from app.models import CommercialOutcome, Project

router = APIRouter(tags=["outcomes"])


class OutcomeRequest(BaseModel):
    outcome_type: CommercialOutcomeType
    source: str = Field(min_length=1, max_length=120)
    observed_at: datetime | None = None
    contact_candidate_id: UUID | None = None
    commercial_motion_id: UUID | None = None
    loss_reason: LossReason | None = None
    notes: str | None = Field(default=None, max_length=4000)


@router.get("/projects/{project_id}/outcomes")
def list_outcomes(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    if session.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(project_id)})
    rows = session.scalars(
        sa.select(CommercialOutcome).where(CommercialOutcome.project_id == project_id).order_by(CommercialOutcome.observed_at.desc())
    ).all()
    return {
        "project_id": str(project_id),
        "items": [
            {
                "id": str(row.id),
                "outcome_type": row.outcome_type.value,
                "loss_reason": row.loss_reason.value if row.loss_reason else None,
                "source": row.source,
                "observed_at": row.observed_at.isoformat(),
                "contact_candidate_id": str(row.contact_candidate_id) if row.contact_candidate_id else None,
                "commercial_motion_id": str(row.commercial_motion_id) if row.commercial_motion_id else None,
                "notes": row.notes,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/projects/{project_id}/outcomes")
def record_outcome(
    project_id: UUID,
    payload: OutcomeRequest,
    _policy=Depends(require_internal_mutation_allowed),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        row = CommercialOutcomeService(session).record(
            project_id=project_id,
            outcome_type=payload.outcome_type,
            source=payload.source,
            observed_at=payload.observed_at,
            contact_candidate_id=payload.contact_candidate_id,
            commercial_motion_id=payload.commercial_motion_id,
            loss_reason=payload.loss_reason,
            notes=payload.notes,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail={"code": "OUTCOME_REJECTED", "message": str(exc)}) from exc
    return {"status": "recorded", "id": str(row.id), "outcome_type": row.outcome_type.value, "observed_at": row.observed_at.isoformat()}
