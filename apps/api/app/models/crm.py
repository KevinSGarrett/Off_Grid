from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import CRMPromotionState, CRMObjectType, IntegrationMode, SyncStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class CRMRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crm_records"
    __table_args__ = (
        sa.UniqueConstraint("crm_system", "object_type", "external_id", name="uq_crm_external_object"),
        sa.UniqueConstraint("crm_system", "object_type", "canonical_key", name="uq_crm_canonical_object"),
    )

    crm_system: Mapped[str] = mapped_column(sa.String(80), nullable=False, default="pipedrive")
    object_type: Mapped[CRMObjectType] = mapped_column(
        enum_column(CRMObjectType, "crm_object_type"), nullable=False
    )
    promotion_state: Mapped[CRMPromotionState] = mapped_column(
        enum_column(CRMPromotionState, "crm_promotion_state"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(sa.String(160))
    canonical_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="SET NULL"))
    organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    person_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("persons.id", ondelete="SET NULL"))
    sync_status: Mapped[SyncStatus] = mapped_column(
        enum_column(SyncStatus, "crm_record_sync_status"), nullable=False, default=SyncStatus.PENDING
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class CRMSyncAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crm_sync_attempts"
    __table_args__ = (
        sa.UniqueConstraint("idempotency_key", name="uq_crm_sync_idempotency_key"),
        sa.Index("ix_crm_sync_record_time", "crm_record_id", "created_at"),
    )

    crm_record_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("crm_records.id", ondelete="SET NULL")
    )
    pipeline_run_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    mode: Mapped[IntegrationMode] = mapped_column(
        enum_column(IntegrationMode, "crm_sync_mode"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    payload_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    request_payload: Mapped[dict | None] = mapped_column(sa.JSON)
    response_payload: Mapped[dict | None] = mapped_column(sa.JSON)
    status: Mapped[SyncStatus] = mapped_column(
        enum_column(SyncStatus, "crm_sync_attempt_status"), nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(sa.String(120))
    error_detail: Mapped[str | None] = mapped_column(sa.Text)
    attempted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
