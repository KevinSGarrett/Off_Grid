from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.states import (
    ConfidenceState,
    EvidenceClassification,
    MaskingPolicy,
    PIIClass,
    ScoringTreatment,
    ValidationState,
    ValueType,
)
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class SourceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        sa.UniqueConstraint("source_type", "content_sha256", name="uq_source_document_type_hash"),
        sa.Index("ix_source_documents_external", "source_system", "external_id"),
    )

    source_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    source_system: Mapped[str | None] = mapped_column(sa.String(80))
    external_id: Mapped[str | None] = mapped_column(sa.String(160))
    report_type: Mapped[str | None] = mapped_column(sa.String(120))
    original_filename: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    content_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    blob_ref: Mapped[str] = mapped_column(sa.String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(sa.String(120))
    byte_size: Mapped[int | None] = mapped_column(sa.BigInteger)
    report_date: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    parser_version: Mapped[str | None] = mapped_column(sa.String(80))
    is_synthetic: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_private: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    observations: Mapped[list["SourceObservation"]] = relationship(back_populates="document")
    evidence: Mapped[list["SourceEvidence"]] = relationship(back_populates="document")


class SourceObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_observations"
    __table_args__ = (
        sa.UniqueConstraint("observation_fingerprint", name="uq_source_observation_fingerprint"),
        sa.Index("ix_source_observation_field", "field_name"),
        sa.Index("ix_source_observation_project", "project_id"),
        sa.Index("ix_source_observation_org", "organization_id"),
        sa.Index("ix_source_observation_person", "person_id"),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="confidence_score_range",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="SET NULL"))
    organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    person_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("persons.id", ondelete="SET NULL"))
    field_name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    value_type: Mapped[ValueType] = mapped_column(enum_column(ValueType, "value_type"), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(sa.Text)
    normalized_text: Mapped[str | None] = mapped_column(sa.Text)
    normalized_integer: Mapped[int | None] = mapped_column(sa.BigInteger)
    normalized_decimal: Mapped[Decimal | None] = mapped_column(sa.Numeric(24, 6))
    normalized_boolean: Mapped[bool | None] = mapped_column(sa.Boolean)
    normalized_date: Mapped[date | None] = mapped_column(sa.Date)
    normalized_datetime: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    currency_code: Mapped[str | None] = mapped_column(sa.String(3))
    unit: Mapped[str | None] = mapped_column(sa.String(40))
    observation_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    evidence_classification: Mapped[EvidenceClassification] = mapped_column(
        enum_column(EvidenceClassification, "evidence_classification"), nullable=False
    )
    confidence_state: Mapped[ConfidenceState] = mapped_column(
        enum_column(ConfidenceState, "confidence_state"), nullable=False, default=ConfidenceState.UNKNOWN
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    confidence_reason: Mapped[str | None] = mapped_column(sa.Text)
    validation_state: Mapped[ValidationState] = mapped_column(
        enum_column(ValidationState, "validation_state"),
        nullable=False,
        default=ValidationState.UNVALIDATED,
    )
    scoring_treatment: Mapped[ScoringTreatment] = mapped_column(
        enum_column(ScoringTreatment, "scoring_treatment"),
        nullable=False,
        default=ScoringTreatment.REVIEW,
    )
    decision_eligible: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    decision_eligibility_reason: Mapped[str | None] = mapped_column(sa.Text)
    observed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    freshness_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    is_synthetic: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    document: Mapped[SourceDocument] = relationship(back_populates="observations")
    evidence: Mapped[list["SourceEvidence"]] = relationship(back_populates="observation")


class SourceEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_evidence"
    __table_args__ = (
        sa.UniqueConstraint("evidence_fingerprint", name="uq_source_evidence_fingerprint"),
        sa.CheckConstraint("page_number IS NULL OR page_number >= 1", name="page_positive"),
    )

    document_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False
    )
    observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="CASCADE")
    )
    page_number: Mapped[int | None] = mapped_column(sa.Integer)
    section_name: Mapped[str | None] = mapped_column(sa.String(240))
    excerpt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    char_start: Mapped[int | None] = mapped_column(sa.Integer)
    char_end: Mapped[int | None] = mapped_column(sa.Integer)
    evidence_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    classification: Mapped[EvidenceClassification] = mapped_column(
        enum_column(EvidenceClassification, "source_evidence_classification"), nullable=False
    )
    pii_class: Mapped[PIIClass] = mapped_column(
        enum_column(PIIClass, "source_evidence_pii_class"), nullable=False, default=PIIClass.NONE
    )
    demo_masking_policy: Mapped[MaskingPolicy] = mapped_column(
        enum_column(MaskingPolicy, "source_evidence_masking_policy"),
        nullable=False,
        default=MaskingPolicy.NONE,
    )
    is_permitted_for_decision: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    document: Mapped[SourceDocument] = relationship(back_populates="evidence")
    observation: Mapped[SourceObservation | None] = relationship(back_populates="evidence")
