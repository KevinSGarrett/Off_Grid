from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.domain.states import (
    ActionStatus,
    ConfidenceState,
    EvidenceClassification,
    MotionStatus,
    MotionType,
    VerificationState,
)


@dataclass(frozen=True)
class DemandSignal:
    label: str
    classification: EvidenceClassification
    confidence_state: ConfidenceState
    strongest_product_code: str | None
    strongest_product_fit: Decimal | None
    rationale: str
    missing_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class MotionFieldState:
    key: str
    value: str
    verification_state: VerificationState
    rationale: str


@dataclass(frozen=True)
class CommercialMotionResult:
    motion_id: UUID
    motion_type: MotionType
    status: MotionStatus
    organization_id: UUID | None
    organization_name: str | None
    demand_strength: str | None
    confidence_state: ConfidenceState
    summary: str
    fields: tuple[MotionFieldState, ...]


@dataclass(frozen=True)
class NextBestActionResult:
    action_id: UUID
    action_type: str
    motion_type: MotionType
    status: ActionStatus
    priority: int
    owner: str
    execution_mode: str
    reason: str
    dependency_action_type: str | None
    dependency_action_id: UUID | None
    source_evidence_id: UUID | None
    external_evidence_id: UUID | None
    immediately_executable: bool


@dataclass(frozen=True)
class FirstCallKit:
    version: str
    target_candidate_id: UUID | None
    target_person_name: str
    target_status: str
    objective: str
    questions: tuple[str, ...]
    after_call_capture: tuple[str, ...]
    safeguards: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OutcomeFeedbackModel:
    version: str
    contact_outcomes: tuple[str, ...]
    project_outcomes: tuple[str, ...]
    commercial_outcomes: tuple[str, ...]
    loss_reasons: tuple[str, ...]
    stored_outcome_count: int
    predictive_ml_trained: bool
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CommercialWorkflowResult:
    workflow_version: str
    project_id: UUID
    project_external_id: str
    demand_signal: DemandSignal
    contractor_motion: CommercialMotionResult
    rental_house_motion: CommercialMotionResult
    next_actions: tuple[NextBestActionResult, ...]
    next_best_action: NextBestActionResult
    first_call_kit: FirstCallKit
    decision_changing_unknowns: tuple[str, ...]
    outcome_feedback: OutcomeFeedbackModel
    external_writes_executed: int
    outreach_messages_sent: int
    notes: tuple[str, ...] = field(default_factory=tuple)
