from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import CommercialOutcomeType, LossReason
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class CommercialOutcome(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commercial_outcomes"
    __table_args__ = (sa.Index("ix_commercial_outcome_project_time", "project_id", "observed_at"),)

    project_id: Mapped[UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    contact_candidate_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("contact_candidates.id", ondelete="SET NULL")
    )
    commercial_motion_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("commercial_motions.id", ondelete="SET NULL")
    )
    outcome_type: Mapped[CommercialOutcomeType] = mapped_column(
        enum_column(CommercialOutcomeType, "commercial_outcome_type"), nullable=False
    )
    loss_reason: Mapped[LossReason | None] = mapped_column(enum_column(LossReason, "loss_reason"))
    source: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(sa.Text)
