from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.states import (
    ConfidenceState,
    EvidenceClassification,
    ExceptionResolutionAction,
    ExceptionStatus,
    QualityFlagState,
    QualitySeverity,
    VerificationState,
)
from app.schemas.common import EntityRead


class ExternalEvidenceRead(EntityRead):
    project_id: UUID | None = None
    organization_id: UUID | None = None
    person_id: UUID | None = None
    source_url: str
    source_title: str | None = None
    publisher: str | None = None
    source_type: str
    claim: str
    classification: EvidenceClassification
    verification_state: VerificationState
    confidence_state: ConfidenceState
    confidence_score: Decimal | None = None
    retrieved_at: datetime
    expires_at: datetime | None = None


class QualityFlagRead(EntityRead):
    rule_code: str
    severity: QualitySeverity
    state: QualityFlagState
    project_id: UUID | None = None
    organization_id: UUID | None = None
    person_id: UUID | None = None
    observation_id: UUID | None = None
    title: str
    detail: str
    decision_impact: str | None = None
    blocks_progression: bool
    first_detected_at: datetime
    resolved_at: datetime | None = None


class WorkflowExceptionRead(EntityRead):
    quality_flag_id: UUID | None = None
    pipeline_run_id: UUID | None = None
    project_id: UUID | None = None
    exception_type: str
    status: ExceptionStatus
    recommended_action: ExceptionResolutionAction
    priority: int
    summary: str
    detail: str | None = None
    owner: str | None = None
