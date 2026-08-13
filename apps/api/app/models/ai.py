from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import AIClaimStatus, EvidenceClassification, RunStatus, ValidationState
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class PromptRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prompt_runs"
    __table_args__ = (sa.Index("ix_prompt_run_task_time", "task", "started_at"),)

    pipeline_run_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    task: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    prompt_name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    model_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    input_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    response_id: Mapped[str | None] = mapped_column(sa.String(200))
    status: Mapped[RunStatus] = mapped_column(
        enum_column(RunStatus, "prompt_run_status"), nullable=False, default=RunStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer)
    error_code: Mapped[str | None] = mapped_column(sa.String(120))
    error_detail: Mapped[str | None] = mapped_column(sa.Text)


class AIClaim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_claims"
    __table_args__ = (sa.Index("ix_ai_claim_run_status", "prompt_run_id", "status"),)

    prompt_run_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("prompt_runs.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="SET NULL"))
    organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    person_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("persons.id", ondelete="SET NULL"))
    claim_type: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    claim_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    classification: Mapped[EvidenceClassification] = mapped_column(
        enum_column(EvidenceClassification, "ai_claim_classification"), nullable=False
    )
    validation_state: Mapped[ValidationState] = mapped_column(
        enum_column(ValidationState, "ai_claim_validation_state"),
        nullable=False,
        default=ValidationState.UNVALIDATED,
    )
    status: Mapped[AIClaimStatus] = mapped_column(
        enum_column(AIClaimStatus, "ai_claim_status"), nullable=False, default=AIClaimStatus.PROPOSED
    )
    accepted_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )
    rejection_reason: Mapped[str | None] = mapped_column(sa.Text)


class AIClaimEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_claim_evidence"
    __table_args__ = (
        sa.UniqueConstraint("ai_claim_id", "source_evidence_id", name="uq_ai_claim_source_evidence"),
    )

    ai_claim_id: Mapped[UUID] = mapped_column(sa.ForeignKey("ai_claims.id", ondelete="CASCADE"), nullable=False)
    source_evidence_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("source_evidence.id", ondelete="CASCADE"), nullable=False
    )


class AIUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_usage"
    __table_args__ = (sa.UniqueConstraint("prompt_run_id", name="uq_ai_usage_prompt_run"),)

    prompt_run_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("prompt_runs.id", ondelete="CASCADE"), nullable=False
    )
    input_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6))
