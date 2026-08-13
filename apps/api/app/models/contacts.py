from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import ContactState, VerificationState
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class ContactCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contact_candidates"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "person_id", name="uq_contact_candidate_project_person"),
        sa.CheckConstraint("candidate_score IS NULL OR (candidate_score >= 0 AND candidate_score <= 100)", name="candidate_score_range"),
        sa.Index("ix_contact_candidate_project_rank", "project_id", "rank"),
    )

    project_id: Mapped[UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    person_id: Mapped[UUID] = mapped_column(sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    state: Mapped[ContactState] = mapped_column(
        enum_column(ContactState, "contact_candidate_state"),
        nullable=False,
        default=ContactState.DISCOVERED,
    )
    rank: Mapped[int | None] = mapped_column(sa.Integer)
    candidate_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 3))
    target_persona: Mapped[str | None] = mapped_column(sa.String(160))
    rationale: Mapped[str | None] = mapped_column(sa.Text)
    is_current: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)


class ContactAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contact_assessments"
    __table_args__ = (sa.Index("ix_contact_assessment_candidate_time", "candidate_id", "assessed_at"),)

    candidate_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("contact_candidates.id", ondelete="CASCADE"), nullable=False
    )
    employment_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "contact_employment_verification"), nullable=False
    )
    project_association_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "contact_project_verification"), nullable=False
    )
    role_relevance_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "contact_role_verification"), nullable=False
    )
    rental_authority_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "contact_authority_verification"), nullable=False
    )
    assessed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    explanation: Mapped[str | None] = mapped_column(sa.Text)
    is_current: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)


class VerificationEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "verification_events"
    __table_args__ = (sa.Index("ix_verification_event_person_time", "person_id", "verified_at"),)

    candidate_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("contact_candidates.id", ondelete="SET NULL")
    )
    person_id: Mapped[UUID] = mapped_column(sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="SET NULL"))
    dimension: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    verification_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    outcome: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "verification_event_outcome"), nullable=False
    )
    source_evidence_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_evidence.id", ondelete="SET NULL")
    )
    external_evidence_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("external_evidence.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(sa.Text)
    verified_by: Mapped[str | None] = mapped_column(sa.String(160))
    verified_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
