from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import EvidenceClassification, ProjectState, VerificationState
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class ProjectGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_groups"
    __table_args__ = (sa.UniqueConstraint("canonical_key", name="uq_project_group_canonical_key"),)

    canonical_name: Mapped[str] = mapped_column(sa.String(320), nullable=False)
    normalized_name: Mapped[str] = mapped_column(sa.String(320), nullable=False, index=True)
    canonical_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    group_type: Mapped[str] = mapped_column(sa.String(60), nullable=False, default="CAMPUS")
    description: Mapped[str | None] = mapped_column(sa.Text)


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        sa.UniqueConstraint("canonical_key", name="uq_project_canonical_key"),
        sa.UniqueConstraint("source_system", "external_id", name="uq_project_source_external_id"),
        sa.Index("ix_project_stage", "state", "stage"),
    )

    project_group_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("project_groups.id", ondelete="SET NULL")
    )
    canonical_name: Mapped[str] = mapped_column(sa.String(400), nullable=False)
    normalized_name: Mapped[str] = mapped_column(sa.String(400), nullable=False, index=True)
    canonical_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    source_system: Mapped[str | None] = mapped_column(sa.String(80))
    external_id: Mapped[str | None] = mapped_column(sa.String(160))
    state: Mapped[ProjectState] = mapped_column(
        enum_column(ProjectState, "project_state"), nullable=False, default=ProjectState.INGESTED
    )
    stage: Mapped[str | None] = mapped_column(sa.String(160))
    category: Mapped[str | None] = mapped_column(sa.String(120))
    city: Mapped[str | None] = mapped_column(sa.String(120))
    region: Mapped[str | None] = mapped_column(sa.String(120))
    country_code: Mapped[str | None] = mapped_column(sa.String(2))
    reported_value: Mapped[Decimal | None] = mapped_column(sa.Numeric(24, 2))
    currency_code: Mapped[str | None] = mapped_column(sa.String(3))
    start_date: Mapped[date | None] = mapped_column(sa.Date)
    completion_date: Mapped[date | None] = mapped_column(sa.Date)
    phase_label: Mapped[str | None] = mapped_column(sa.String(120))
    phase_start_number: Mapped[int | None] = mapped_column(sa.Integer)
    phase_end_number: Mapped[int | None] = mapped_column(sa.Integer)
    is_synthetic: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)


class ProjectRelationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_relationships"
    __table_args__ = (
        sa.UniqueConstraint(
            "parent_project_id", "child_project_id", "relationship_type", name="uq_project_relationship"
        ),
        sa.CheckConstraint("parent_project_id <> child_project_id", name="not_self_relationship"),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="project_relationship_confidence_range",
        ),
    )

    parent_project_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    child_project_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    verification_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "project_relationship_verification"),
        nullable=False,
        default=VerificationState.UNKNOWN,
    )
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    rationale: Mapped[str | None] = mapped_column(sa.Text)


class ProjectSignal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_signals"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "signal_key", "source_observation_id", name="uq_project_signal_source"),
        sa.CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)", name="confidence_range"),
    )

    project_id: Mapped[UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    signal_key: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    signal_value: Mapped[str | None] = mapped_column(sa.String(400))
    classification: Mapped[EvidenceClassification] = mapped_column(
        enum_column(EvidenceClassification, "project_signal_classification"), nullable=False
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )
    explanation: Mapped[str | None] = mapped_column(sa.Text)


class ProjectOrganization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_organizations"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "organization_id", "role", name="uq_project_organization_role"),
    )

    project_id: Mapped[UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    verification_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "project_organization_verification"),
        nullable=False,
        default=VerificationState.UNKNOWN,
    )
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )


class ProjectPerson(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_persons"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "person_id", "role", name="uq_project_person_role"),
    )

    project_id: Mapped[UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    person_id: Mapped[UUID] = mapped_column(sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    role: Mapped[str | None] = mapped_column(sa.String(160))
    association_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "project_person_association_state"),
        nullable=False,
        default=VerificationState.UNKNOWN,
    )
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )
