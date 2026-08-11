from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID


class GroundingStatus(StrEnum):
    VALID = "VALID"
    UNSUPPORTED = "UNSUPPORTED"
    CONFLICTED = "CONFLICTED"


class AIRunStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    DISABLED = "DISABLED"
    BUDGET_BLOCKED = "BUDGET_BLOCKED"
    GROUNDING_REJECTED = "GROUNDING_REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class UsageMetrics:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass(frozen=True, slots=True)
class FunctionCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class OpenAIResponseEnvelope:
    response_id: str | None
    model_id: str | None
    output_text: str
    output_items: tuple[dict[str, Any], ...] = ()
    function_calls: tuple[FunctionCall, ...] = ()
    usage: UsageMetrics = field(default_factory=UsageMetrics)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    excerpt: str
    source_kind: str
    page_number: int | None = None
    classification: str | None = None
    pii_class: str | None = None


@dataclass(frozen=True, slots=True)
class GroundingIssue:
    claim_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class GroundingReport:
    status: GroundingStatus
    valid_claim_ids: tuple[str, ...]
    issues: tuple[GroundingIssue, ...]

    @property
    def is_valid(self) -> bool:
        # CONFLICTED is a truthful, evidence-backed state, not an unsupported claim. Preserve the
        # conflict in the report while allowing the caller to receive the grounded answer.
        return self.status is not GroundingStatus.UNSUPPORTED


@dataclass(frozen=True, slots=True)
class AIRunResult:
    status: AIRunStatus
    task: str
    model_id: str | None
    prompt_run_id: UUID | None
    parsed: Any | None
    grounding: GroundingReport | None
    estimated_cost_usd: Decimal
    fallback_reason: str | None = None
    external_request_executed: bool = False
