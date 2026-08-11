from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import (
    ConfidenceState,
    EvidenceClassification,
    ExceptionResolutionAction,
    ExceptionStatus,
    MaskingPolicy,
    PIIClass,
    QualityFlagState,
    QualitySeverity,
    ValidationState,
    VerificationState,
)
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class ExternalEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "external_evidence"
    __table_args__ = (
        sa.UniqueConstraint("evidence_fingerprint", name="uq_external_evidence_fingerprint"),
        sa.Index("ix_external_evidence_subject", "project_id", "organization_id", "person_id"),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="confidence_score_range",
        ),
    )

    project_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="SET NULL"))
    organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    person_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("persons.id", ondelete="SET NULL"))
    source_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_title: Mapped[str | None] = mapped_column(sa.String(600))
    publisher: Mapped[str | None] = mapped_column(sa.String(300))
    source_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    claim: Mapped[str] = mapped_column(sa.Text, nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    classification: Mapped[EvidenceClassification] = mapped_column(
        enum_column(EvidenceClassification, "external_evidence_classification"), nullable=False
    )
    verification_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "external_evidence_verification_state"),
        nullable=False,
        default=VerificationState.UNKNOWN,
    )
    confidence_state: Mapped[ConfidenceState] = mapped_column(
        enum_column(ConfidenceState, "external_evidence_confidence_state"),
        nullable=False,
        default=ConfidenceState.UNKNOWN,
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    retrieved_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    pii_class: Mapped[PIIClass] = mapped_column(
        enum_column(PIIClass, "external_evidence_pii_class"), nullable=False, default=PIIClass.NONE
    )
    demo_masking_policy: Mapped[MaskingPolicy] = mapped_column(
        enum_column(MaskingPolicy, "external_evidence_masking_policy"),
        nullable=False,
        default=MaskingPolicy.NONE,
    )


class QualityFlag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quality_flags"
    __table_args__ = (
        sa.Index("ix_quality_flag_open_severity", "state", "severity"),
        sa.Index("ix_quality_flag_subject", "project_id", "organization_id", "person_id"),
    )

    rule_code: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    severity: Mapped[QualitySeverity] = mapped_column(
        enum_column(QualitySeverity, "quality_severity"), nullable=False
    )
    state: Mapped[QualityFlagState] = mapped_column(
        enum_column(QualityFlagState, "quality_flag_state"),
        nullable=False,
        default=QualityFlagState.OPEN,
    )
    project_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"))
    organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE")
    )
    person_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("persons.id", ondelete="CASCADE"))
    observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )
    source_evidence_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_evidence.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    detail: Mapped[str] = mapped_column(sa.Text, nullable=False)
    decision_impact: Mapped[str | None] = mapped_column(sa.String(40))
    blocks_progression: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    first_detected_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class WorkflowException(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_exceptions"
    __table_args__ = (sa.Index("ix_workflow_exception_queue", "status", "priority"),)

    quality_flag_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("quality_flags.id", ondelete="SET NULL")
    )
    pipeline_run_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    project_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"))
    exception_type: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    status: Mapped[ExceptionStatus] = mapped_column(
        enum_column(ExceptionStatus, "workflow_exception_status"),
        nullable=False,
        default=ExceptionStatus.OPEN,
    )
    recommended_action: Mapped[ExceptionResolutionAction] = mapped_column(
        enum_column(ExceptionResolutionAction, "exception_resolution_action"), nullable=False
    )
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=50)
    summary: Mapped[str] = mapped_column(sa.String(400), nullable=False)
    detail: Mapped[str | None] = mapped_column(sa.Text)
    owner: Mapped[str | None] = mapped_column(sa.String(160))
    resolution_note: Mapped[str | None] = mapped_column(sa.Text)
    resolved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
