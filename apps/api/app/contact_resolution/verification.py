from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import ContactState, VerificationState
from app.models import ContactAssessment, ContactCandidate, VerificationEvent


DIRECT_AUTHORITY_TYPES = {
    "PHONE_CONFIRMATION",
    "EMAIL_CONFIRMATION",
    "PROJECT_PROCUREMENT_ASSIGNMENT",
}
SUPPORTED_VERIFICATION_TYPES = {
    "PHONE_CONFIRMATION",
    "EMAIL_CONFIRMATION",
    "PROJECT_PROCUREMENT_ASSIGNMENT",
    "MANUAL_RESEARCH",
    "COMPANY_SOURCE",
    "PROJECT_SOURCE",
    "APOLLO",
}
SUPPORTED_DIMENSIONS = {
    "employment",
    "project_association",
    "role_relevance",
    "rental_authority",
}


class ContactVerificationService:
    """Record human/authorized verification without performing prospect outreach.

    The service only records the result of work performed outside the application. It never calls,
    emails, or otherwise contacts a prospect. Rental authority is fail-closed: a VERIFIED authority
    outcome requires an explicit direct-confirmation/procurement source and a candidate whose prior
    employment, project association, and role relevance gates are already satisfied.
    """

    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        *,
        candidate_id: UUID,
        dimension: str,
        verification_type: str,
        outcome: VerificationState,
        verified_by: str,
        note: str,
        verified_at: datetime | None = None,
        source_evidence_id: UUID | None = None,
        external_evidence_id: UUID | None = None,
    ) -> VerificationEvent:
        dimension = dimension.strip().lower()
        verification_type = verification_type.strip().upper()
        verified_by = verified_by.strip()
        note = note.strip()

        if dimension not in SUPPORTED_DIMENSIONS:
            raise ValueError(f"Unsupported contact verification dimension: {dimension}")
        if verification_type not in SUPPORTED_VERIFICATION_TYPES:
            raise ValueError(f"Unsupported contact verification type: {verification_type}")
        if not verified_by:
            raise ValueError("verified_by is required for human/authorized verification")
        if not note:
            raise ValueError("A verification note is required")

        candidate = self.session.get(ContactCandidate, candidate_id)
        if candidate is None:
            raise ValueError(f"Contact candidate not found: {candidate_id}")
        assessment = self.session.scalar(
            sa.select(ContactAssessment).where(
                ContactAssessment.candidate_id == candidate.id,
                ContactAssessment.is_current.is_(True),
            )
        )
        if assessment is None:
            raise ValueError("Current ContactAssessment is required before direct verification")

        if dimension == "rental_authority" and outcome == VerificationState.VERIFIED:
            if verification_type not in DIRECT_AUTHORITY_TYPES:
                raise ValueError(
                    "Rental authority may be VERIFIED only from direct phone/email confirmation "
                    "or explicit project procurement assignment evidence"
                )
            if assessment.employment_state != VerificationState.VERIFIED:
                raise ValueError("Employment must be VERIFIED before rental authority can be VERIFIED")
            if assessment.project_association_state != VerificationState.VERIFIED:
                raise ValueError("Project association must be VERIFIED before rental authority can be VERIFIED")
            if assessment.role_relevance_state not in {
                VerificationState.SUPPORTED,
                VerificationState.VERIFIED,
            }:
                raise ValueError("Role relevance must be supported before rental authority can be VERIFIED")

        timestamp = verified_at or datetime.now(timezone.utc)
        event = VerificationEvent(
            candidate_id=candidate.id,
            person_id=candidate.person_id,
            project_id=candidate.project_id,
            dimension=dimension,
            verification_type=verification_type,
            outcome=outcome,
            source_evidence_id=source_evidence_id,
            external_evidence_id=external_evidence_id,
            note=note,
            verified_by=verified_by,
            verified_at=timestamp,
        )
        self.session.add(event)

        self._apply_dimension(assessment, dimension, outcome)
        assessment.assessed_at = timestamp
        assessment.explanation = self._append_explanation(
            assessment.explanation,
            dimension=dimension,
            verification_type=verification_type,
            outcome=outcome,
            verified_by=verified_by,
            note=note,
            verified_at=timestamp,
        )
        candidate.state = self._derive_contact_state(assessment)
        self.session.flush()
        return event

    @staticmethod
    def _apply_dimension(
        assessment: ContactAssessment,
        dimension: str,
        outcome: VerificationState,
    ) -> None:
        mapping = {
            "employment": "employment_state",
            "project_association": "project_association_state",
            "role_relevance": "role_relevance_state",
            "rental_authority": "rental_authority_state",
        }
        setattr(assessment, mapping[dimension], outcome)

    @staticmethod
    def _derive_contact_state(assessment: ContactAssessment) -> ContactState:
        if assessment.employment_state != VerificationState.VERIFIED:
            return ContactState.DISCOVERED
        if assessment.project_association_state != VerificationState.VERIFIED:
            return ContactState.EMPLOYMENT_VERIFIED
        if assessment.role_relevance_state not in {
            VerificationState.SUPPORTED,
            VerificationState.VERIFIED,
        }:
            return ContactState.PROJECT_ASSOCIATION_VERIFIED
        if assessment.rental_authority_state == VerificationState.VERIFIED:
            return ContactState.AUTHORITY_VERIFIED
        return ContactState.ROLE_RELEVANT

    @staticmethod
    def _append_explanation(
        existing: str | None,
        *,
        dimension: str,
        verification_type: str,
        outcome: VerificationState,
        verified_by: str,
        note: str,
        verified_at: datetime,
    ) -> str:
        try:
            payload = json.loads(existing) if existing else {}
        except json.JSONDecodeError:
            payload = {"prior_explanation": existing}
        events = payload.setdefault("direct_verification_events", [])
        events.append(
            {
                "dimension": dimension,
                "verification_type": verification_type,
                "outcome": outcome.value,
                "verified_by": verified_by,
                "note": note,
                "verified_at": verified_at.isoformat(),
            }
        )
        return json.dumps(payload, sort_keys=True)
