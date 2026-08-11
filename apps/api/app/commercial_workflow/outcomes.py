from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import CommercialOutcomeType, LossReason
from app.models import CommercialMotion, CommercialOutcome, ContactCandidate, Project


CONTACT_OUTCOMES = {
    CommercialOutcomeType.RIGHT_PERSON,
    CommercialOutcomeType.WRONG_PERSON,
    CommercialOutcomeType.LEFT_COMPANY,
}
PROJECT_OUTCOMES = {
    CommercialOutcomeType.GOOD_FIT,
    CommercialOutcomeType.POOR_FIT,
    CommercialOutcomeType.NO_NEED,
    CommercialOutcomeType.NOT_NOW,
}
COMMERCIAL_OUTCOMES = {
    CommercialOutcomeType.NO_RESPONSE,
    CommercialOutcomeType.RESPONDED,
    CommercialOutcomeType.INTERESTED,
    CommercialOutcomeType.DEMO_BOOKED,
    CommercialOutcomeType.DEMO_COMPLETED,
    CommercialOutcomeType.RENTAL_PARTNER_IDENTIFIED,
    CommercialOutcomeType.WON,
    CommercialOutcomeType.LOST,
}


class CommercialOutcomeService:
    """Record observed commercial feedback without fabricating activity.

    Wave 09 creates the capture path only. A row is written only when the caller supplies an
    observed outcome and a source. The service intentionally performs no model training.
    """

    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        *,
        project_id: UUID,
        outcome_type: CommercialOutcomeType | str,
        source: str,
        observed_at: datetime | None = None,
        contact_candidate_id: UUID | None = None,
        commercial_motion_id: UUID | None = None,
        loss_reason: LossReason | str | None = None,
        notes: str | None = None,
    ) -> CommercialOutcome:
        outcome = CommercialOutcomeType(outcome_type)
        reason = LossReason(loss_reason) if loss_reason is not None else None
        if not source.strip():
            raise ValueError("Outcome source is required")
        if self.session.get(Project, project_id) is None:
            raise ValueError("Unknown project")
        if contact_candidate_id is not None and self.session.get(ContactCandidate, contact_candidate_id) is None:
            raise ValueError("Unknown contact candidate")
        if commercial_motion_id is not None and self.session.get(CommercialMotion, commercial_motion_id) is None:
            raise ValueError("Unknown commercial motion")
        if outcome is CommercialOutcomeType.LOST and reason is None:
            raise ValueError("LOST outcomes require a loss reason")
        if outcome is not CommercialOutcomeType.LOST and reason is not None:
            raise ValueError("loss_reason is permitted only for LOST outcomes")
        if outcome in CONTACT_OUTCOMES and contact_candidate_id is None:
            raise ValueError("Contact outcomes require contact_candidate_id")
        if outcome in COMMERCIAL_OUTCOMES and commercial_motion_id is None:
            raise ValueError("Commercial outcomes require commercial_motion_id")

        row = CommercialOutcome(
            project_id=project_id,
            contact_candidate_id=contact_candidate_id,
            commercial_motion_id=commercial_motion_id,
            outcome_type=outcome,
            loss_reason=reason,
            source=source.strip(),
            observed_at=observed_at or datetime.now(timezone.utc),
            notes=notes,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def count(self, project_id: UUID) -> int:
        return int(
            self.session.scalar(
                sa.select(sa.func.count()).select_from(CommercialOutcome).where(
                    CommercialOutcome.project_id == project_id
                )
            )
            or 0
        )

    def feature_outcome_export(self, project_id: UUID) -> tuple[dict[str, str | None], ...]:
        """Return structured historical labels for future analysis/calibration, not ML training."""
        rows = self.session.scalars(
            sa.select(CommercialOutcome)
            .where(CommercialOutcome.project_id == project_id)
            .order_by(CommercialOutcome.observed_at, CommercialOutcome.created_at)
        ).all()
        return tuple(
            {
                "project_id": str(row.project_id),
                "contact_candidate_id": str(row.contact_candidate_id) if row.contact_candidate_id else None,
                "commercial_motion_id": str(row.commercial_motion_id) if row.commercial_motion_id else None,
                "outcome_type": row.outcome_type.value,
                "loss_reason": row.loss_reason.value if row.loss_reason else None,
                "source": row.source,
                "observed_at": row.observed_at.isoformat(),
            }
            for row in rows
        )
