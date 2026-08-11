from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import ConfidenceState, EvidenceClassification
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class OpportunityAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_assessments"
    __table_args__ = (
        sa.CheckConstraint("commercial_fit_score >= 0 AND commercial_fit_score <= 100", name="fit_score_range"),
        sa.CheckConstraint("data_confidence_score >= 0 AND data_confidence_score <= 100", name="confidence_score_range"),
        sa.Index("ix_opportunity_assessment_project_current", "project_id", "computed_at"),
    )

    project_id: Mapped[UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scoring_config_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("scoring_configs.id", ondelete="SET NULL")
    )
    commercial_fit_score: Mapped[Decimal] = mapped_column(sa.Numeric(6, 3), nullable=False)
    data_confidence_score: Mapped[Decimal] = mapped_column(sa.Numeric(6, 3), nullable=False)
    disposition: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    confidence_state: Mapped[ConfidenceState] = mapped_column(
        enum_column(ConfidenceState, "opportunity_confidence_state"), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    explanation: Mapped[str | None] = mapped_column(sa.Text)
    is_current: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)


class AssessmentFactor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_factors"
    __table_args__ = (
        sa.UniqueConstraint("assessment_id", "factor_key", name="uq_assessment_factor_key"),
    )

    assessment_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("opportunity_assessments.id", ondelete="CASCADE"), nullable=False
    )
    factor_key: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    label: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    weight: Mapped[Decimal] = mapped_column(sa.Numeric(8, 4), nullable=False)
    raw_points: Mapped[Decimal] = mapped_column(sa.Numeric(8, 4), nullable=False)
    adjusted_points: Mapped[Decimal] = mapped_column(sa.Numeric(8, 4), nullable=False)
    cap_points: Mapped[Decimal | None] = mapped_column(sa.Numeric(8, 4))
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )
    evidence_classification: Mapped[EvidenceClassification] = mapped_column(
        enum_column(EvidenceClassification, "assessment_factor_classification"), nullable=False
    )
    explanation: Mapped[str | None] = mapped_column(sa.Text)


class ProductFitAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_fit_assessments"
    __table_args__ = (
        sa.UniqueConstraint("opportunity_assessment_id", "product_code", name="uq_product_fit_assessment"),
        sa.CheckConstraint("fit_score >= 0 AND fit_score <= 100", name="fit_score_range"),
    )

    opportunity_assessment_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("opportunity_assessments.id", ondelete="CASCADE"), nullable=False
    )
    product_code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    fit_score: Mapped[Decimal] = mapped_column(sa.Numeric(6, 3), nullable=False)
    fit_band: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    classification: Mapped[EvidenceClassification] = mapped_column(
        enum_column(EvidenceClassification, "product_fit_classification"), nullable=False
    )
    confidence_state: Mapped[ConfidenceState] = mapped_column(
        enum_column(ConfidenceState, "product_fit_confidence_state"), nullable=False
    )
    explanation: Mapped[str | None] = mapped_column(sa.Text)
    missing_evidence: Mapped[str | None] = mapped_column(sa.Text)
