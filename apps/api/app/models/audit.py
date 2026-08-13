from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        sa.Index("ix_audit_event_object_time", "object_type", "object_id", "occurred_at"),
        sa.Index("ix_audit_event_actor_time", "actor_type", "actor_id", "occurred_at"),
    )

    pipeline_run_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    actor_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(sa.String(160))
    action: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    object_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    object_id: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    reason: Mapped[str | None] = mapped_column(sa.Text)
    before_hash: Mapped[str | None] = mapped_column(sa.String(64))
    after_hash: Mapped[str | None] = mapped_column(sa.String(64))
    safe_metadata: Mapped[dict | None] = mapped_column(sa.JSON)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
