from __future__ import annotations

from uuid import UUID

from app.domain.states import ContactPointType, MaskingPolicy, PIIClass, VerificationState
from app.schemas.common import EntityRead


class OrganizationRead(EntityRead):
    canonical_name: str
    normalized_name: str
    canonical_key: str
    organization_type: str | None = None
    status: str


class PersonRead(EntityRead):
    display_name: str
    normalized_name: str
    given_name: str | None = None
    family_name: str | None = None
    current_organization_id: UUID | None = None
    employment_state: VerificationState
    status: str


class PrivateContactPointRead(EntityRead):
    person_id: UUID
    organization_id: UUID | None = None
    contact_type: ContactPointType
    value: str
    normalized_value: str
    pii_class: PIIClass
    demo_masking_policy: MaskingPolicy
    verification_state: VerificationState
    is_generic: bool
    is_primary: bool


class DemoContactPointRead(EntityRead):
    person_id: UUID
    organization_id: UUID | None = None
    contact_type: ContactPointType
    display_value: str | None
    pii_class: PIIClass
    masking_policy_applied: MaskingPolicy
    verification_state: VerificationState
    is_generic: bool
    is_primary: bool
