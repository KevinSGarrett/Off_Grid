from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.states import ContactPointType, MaskingPolicy, PIIClass, VerificationState
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        sa.UniqueConstraint("canonical_key", name="uq_organization_canonical_key"),
        sa.Index("ix_organization_normalized_name", "normalized_name"),
    )

    canonical_name: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    canonical_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    organization_type: Mapped[str | None] = mapped_column(sa.String(80))
    status: Mapped[str] = mapped_column(sa.String(40), nullable=False, default="ACTIVE")
    notes: Mapped[str | None] = mapped_column(sa.Text)


class OrganizationAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_aliases"
    __table_args__ = (
        sa.UniqueConstraint("organization_id", "normalized_alias", name="uq_org_alias_normalized"),
        sa.Index("ix_org_alias_lookup", "normalized_alias"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )
    alias_type: Mapped[str | None] = mapped_column(sa.String(60))


class OrganizationDomain(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_domains"
    __table_args__ = (
        sa.UniqueConstraint("organization_id", "normalized_domain", name="uq_org_domain"),
        sa.Index("ix_org_domain_lookup", "normalized_domain"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    normalized_domain: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    relationship_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "organization_domain_verification_state"),
        nullable=False,
        default=VerificationState.UNKNOWN,
    )
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)


class OrganizationAddress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_addresses"

    organization_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    address_type: Mapped[str | None] = mapped_column(sa.String(60))
    line1: Mapped[str | None] = mapped_column(sa.String(300))
    line2: Mapped[str | None] = mapped_column(sa.String(300))
    city: Mapped[str | None] = mapped_column(sa.String(120))
    region: Mapped[str | None] = mapped_column(sa.String(120))
    postal_code: Mapped[str | None] = mapped_column(sa.String(32))
    country_code: Mapped[str | None] = mapped_column(sa.String(2))
    normalized_address: Mapped[str | None] = mapped_column(sa.String(900), index=True)
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )


class Person(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "persons"
    __table_args__ = (sa.Index("ix_person_normalized_name", "normalized_name"),)

    display_name: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    normalized_name: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    given_name: Mapped[str | None] = mapped_column(sa.String(120))
    family_name: Mapped[str | None] = mapped_column(sa.String(120))
    current_organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    employment_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "person_employment_state"),
        nullable=False,
        default=VerificationState.UNKNOWN,
    )
    status: Mapped[str] = mapped_column(sa.String(40), nullable=False, default="UNKNOWN")


class PersonAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "person_aliases"
    __table_args__ = (
        sa.UniqueConstraint("person_id", "normalized_alias", name="uq_person_alias_normalized"),
        sa.Index("ix_person_alias_lookup", "normalized_alias"),
    )

    person_id: Mapped[UUID] = mapped_column(sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )


class PersonContactPoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "person_contact_points"
    __table_args__ = (
        sa.Index("ix_contact_point_normalized", "contact_type", "normalized_value"),
    )

    person_id: Mapped[UUID] = mapped_column(sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    contact_type: Mapped[ContactPointType] = mapped_column(
        enum_column(ContactPointType, "contact_point_type"), nullable=False
    )
    value: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    normalized_value: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    pii_class: Mapped[PIIClass] = mapped_column(
        enum_column(PIIClass, "contact_point_pii_class"),
        nullable=False,
        default=PIIClass.BUSINESS_CONTACT,
    )
    demo_masking_policy: Mapped[MaskingPolicy] = mapped_column(
        enum_column(MaskingPolicy, "contact_point_masking_policy"),
        nullable=False,
        default=MaskingPolicy.PARTIAL,
    )
    verification_state: Mapped[VerificationState] = mapped_column(
        enum_column(VerificationState, "contact_point_verification_state"),
        nullable=False,
        default=VerificationState.UNKNOWN,
    )
    is_generic: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    source_observation_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("source_observations.id", ondelete="SET NULL")
    )
