from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import ActionStatus, ConfidenceState, MotionStatus, MotionType
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class CommercialMotion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commercial_motions"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "motion_type", name="uq_commercial_motion_project_type"),
    )

    project_id: Mapped[UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    motion_type: Mapped[MotionType] = mapped_column(enum_column(MotionType, "motion_type"), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    status: Mapped[MotionStatus] = mapped_column(
        enum_column(MotionStatus, "motion_status"), nullable=False, default=MotionStatus.UNRESOLVED
    )
    demand_strength: Mapped[str | None] = mapped_column(sa.String(40))
    confidence_state: Mapped[ConfidenceState] = mapped_column(
        enum_column(ConfidenceState, "motion_confidence_state"),
        nullable=False,
        default=ConfidenceState.UNKNOWN,
    )
    owner: Mapped[str | None] = mapped_column(sa.String(160))
    summary: Mapped[str | None] = mapped_column(sa.Text)


class NextAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "next_actions"
    __table_args__ = (sa.Index("ix_next_action_queue", "status", "priority", "due_at"),)

    project_id: Mapped[UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    commercial_motion_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("commercial_motions.id", ondelete="SET NULL")
    )
    dependency_action_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("next_actions.id", ondelete="SET NULL")
    )
    action_type: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    status: Mapped[ActionStatus] = mapped_column(
        enum_column(ActionStatus, "next_action_status"), nullable=False, default=ActionStatus.OPEN
    )
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=50)
    owner: Mapped[str | None] = mapped_column(sa.String(160))
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_evidence_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_evidence.id", ondelete="SET NULL")
    )
    external_evidence_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("external_evidence.id", ondelete="SET NULL")
    )
    due_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
