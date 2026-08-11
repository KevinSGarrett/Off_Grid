from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.domain.states import (
    ConfidenceState,
    EvidenceClassification,
    MaskingPolicy,
    PIIClass,
    ScoringTreatment,
    ValidationState,
    ValueType,
)
from app.schemas.common import EntityRead


class SourceDocumentRead(EntityRead):
    source_type: str
    source_system: str | None = None
    external_id: str | None = None
    report_type: str | None = None
    original_filename: str
    content_sha256: str = Field(min_length=64, max_length=64)
    blob_ref: str
    mime_type: str | None = None
    byte_size: int | None = None
    report_date: datetime | None = None
    imported_at: datetime
    parser_version: str | None = None
    is_synthetic: bool
    is_private: bool


class SourceObservationRead(EntityRead):
    document_id: UUID
    project_id: UUID | None = None
    organization_id: UUID | None = None
    person_id: UUID | None = None
    field_name: str
    value_type: ValueType
    raw_value: str | None = None
    normalized_text: str | None = None
    normalized_integer: int | None = None
    normalized_decimal: Decimal | None = None
    normalized_boolean: bool | None = None
    normalized_date: date | None = None
    normalized_datetime: datetime | None = None
    currency_code: str | None = None
    unit: str | None = None
    evidence_classification: EvidenceClassification
    confidence_state: ConfidenceState
    confidence_score: Decimal | None = None
    confidence_reason: str | None = None
    validation_state: ValidationState
    scoring_treatment: ScoringTreatment
    observed_at: datetime | None = None
    freshness_at: datetime | None = None
    is_synthetic: bool


class SourceEvidenceRead(EntityRead):
    document_id: UUID
    observation_id: UUID | None = None
    page_number: int | None = None
    section_name: str | None = None
    excerpt: str
    classification: EvidenceClassification
    pii_class: PIIClass
    demo_masking_policy: MaskingPolicy
    is_permitted_for_decision: bool
