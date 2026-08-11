from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_internal_mutation_allowed
from app.contact_resolution.verification import ContactVerificationService
from app.domain.states import VerificationState
from app.models import ContactAssessment, ContactCandidate, Person, Project

router = APIRouter(tags=["contacts"])


class VerificationRequest(BaseModel):
    dimension: str
    verification_type: str
    outcome: VerificationState
    verified_by: str = Field(min_length=1, max_length=160)
    note: str = Field(min_length=1, max_length=4000)
    verified_at: datetime | None = None
    source_evidence_id: UUID | None = None
    external_evidence_id: UUID | None = None


@router.get("/projects/{project_id}/contact-candidates")
def get_contact_candidates(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(project_id)})
    rows = session.execute(
        sa.select(ContactCandidate, ContactAssessment, Person)
        .join(Person, ContactCandidate.person_id == Person.id)
        .outerjoin(
            ContactAssessment,
            sa.and_(ContactAssessment.candidate_id == ContactCandidate.id, ContactAssessment.is_current.is_(True)),
        )
        .where(ContactCandidate.project_id == project_id, ContactCandidate.is_current.is_(True))
        .order_by(ContactCandidate.rank.asc().nullslast(), ContactCandidate.candidate_score.desc())
    ).all()
    items = []
    for candidate, assessment, person in rows:
        items.append(
            {
                "candidate_id": str(candidate.id),
                "person_id": str(person.id),
                "organization_id": str(candidate.organization_id) if candidate.organization_id else None,
                "display_name": person.display_name,
                "state": candidate.state.value,
                "rank": candidate.rank,
                "candidate_score": str(candidate.candidate_score) if candidate.candidate_score is not None else None,
                "target_persona": candidate.target_persona,
                "rationale": candidate.rationale,
                "verification": None
                if assessment is None
                else {
                    "employment": assessment.employment_state.value,
                    "project_association": assessment.project_association_state.value,
                    "role_relevance": assessment.role_relevance_state.value,
                    "rental_authority": assessment.rental_authority_state.value,
                    "assessed_at": assessment.assessed_at.isoformat(),
                },
            }
        )
    return {"project_id": str(project_id), "items": items, "count": len(items)}


@router.post("/contacts/{contact_id}/verification")
def verify_contact(
    contact_id: UUID,
    payload: VerificationRequest,
    _policy=Depends(require_internal_mutation_allowed),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        event = ContactVerificationService(session).record(
            candidate_id=contact_id,
            dimension=payload.dimension,
            verification_type=payload.verification_type,
            outcome=payload.outcome,
            verified_by=payload.verified_by,
            note=payload.note,
            verified_at=payload.verified_at,
            source_evidence_id=payload.source_evidence_id,
            external_evidence_id=payload.external_evidence_id,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail={"code": "VERIFICATION_REJECTED", "message": str(exc)}) from exc
    return {
        "status": "recorded",
        "event_id": str(event.id),
        "candidate_id": str(event.candidate_id) if event.candidate_id else None,
        "dimension": event.dimension,
        "verification_type": event.verification_type,
        "outcome": event.outcome.value,
        "verified_at": event.verified_at.isoformat(),
    }
