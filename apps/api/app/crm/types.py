from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.domain.states import CRMPromotionState, CRMObjectType, SyncStatus


@dataclass(frozen=True)
class ReadinessCheck:
    key: str
    passed: bool
    applies_to: tuple[CRMPromotionState, ...]
    rationale: str


@dataclass(frozen=True)
class CRMReadinessResult:
    version: str
    project_id: UUID
    project_external_id: str
    commercial_fit: Decimal
    data_confidence: Decimal
    lead_ready: bool
    deal_ready: bool
    permitted_promotion: CRMPromotionState
    checks: tuple[ReadinessCheck, ...]
    lead_blockers: tuple[str, ...]
    deal_blockers: tuple[str, ...]


@dataclass(frozen=True)
class IntegrationRequest:
    object_type: CRMObjectType | None
    label: str
    method: str
    path: str
    body: dict
    query: dict = field(default_factory=dict)
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    status: SyncStatus = SyncStatus.PREVIEWED
    blocked_reason: str | None = None
    canonical_key: str | None = None


@dataclass(frozen=True)
class PipedrivePreview:
    version: str
    mode: str
    lead_ready: bool
    deal_ready: bool
    requests: tuple[IntegrationRequest, ...]
    external_writes_executed: int
    notes: tuple[str, ...]


@dataclass(frozen=True)
class SheetsPreview:
    version: str
    method: str
    path: str
    query: dict
    body: dict
    columns: tuple[str, ...]
    row: tuple[object, ...]
    external_writes_executed: int = 0


@dataclass(frozen=True)
class FormsPreview:
    version: str
    create_method: str
    create_path: str
    create_body: dict
    batch_update_method: str
    batch_update_path: str
    batch_update_body: dict
    response_ingest_method: str
    response_ingest_path: str
    response_submission_api_supported: bool
    questions: tuple[dict, ...]
    external_writes_executed: int = 0


@dataclass(frozen=True)
class TrelloPreview:
    version: str
    method: str
    path: str
    body: dict
    idempotency_key: str
    external_writes_executed: int = 0


@dataclass(frozen=True)
class Wave10IntegrationResult:
    crm_version: str
    reporting_version: str
    project_id: UUID
    readiness: CRMReadinessResult
    pipedrive: PipedrivePreview
    sheets: SheetsPreview
    forms: FormsPreview
    trello: TrelloPreview
    crm_record_count: int
    crm_sync_attempt_count: int
    audit_event_count: int
    external_writes_executed: int
