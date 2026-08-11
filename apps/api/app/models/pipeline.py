from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import RunStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class PipelineRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (sa.Index("ix_pipeline_run_status_time", "status", "started_at"),)

    run_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    mode: Mapped[str] = mapped_column(sa.String(60), nullable=False, default="LOCAL")
    status: Mapped[RunStatus] = mapped_column(
        enum_column(RunStatus, "pipeline_run_status"), nullable=False, default=RunStatus.PENDING
    )
    correlation_id: Mapped[str] = mapped_column(sa.String(160), nullable=False, unique=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    source_document_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    exception_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(sa.Text)


class PipelineEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_events"
    __table_args__ = (
        sa.UniqueConstraint("pipeline_run_id", "sequence_number", name="uq_pipeline_event_sequence"),
        sa.Index("ix_pipeline_event_run_time", "pipeline_run_id", "occurred_at"),
    )

    pipeline_run_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    stage: Mapped[str | None] = mapped_column(sa.String(120))
    entity_type: Mapped[str | None] = mapped_column(sa.String(80))
    entity_id: Mapped[str | None] = mapped_column(sa.String(80))
    message: Mapped[str | None] = mapped_column(sa.Text)
    safe_metadata: Mapped[dict | None] = mapped_column(sa.JSON)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)


class FieldHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_history"
    __table_args__ = (sa.Index("ix_field_history_entity_field", "entity_type", "entity_id", "field_name"),)

    pipeline_run_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    entity_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    field_name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    previous_value: Mapped[str | None] = mapped_column(sa.Text)
    new_value: Mapped[str | None] = mapped_column(sa.Text)
    change_type: Mapped[str] = mapped_column(sa.String(60), nullable=False, default="UPDATED")
    detected_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    commercial_impact: Mapped[str | None] = mapped_column(sa.String(40))
