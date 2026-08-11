from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.domain.states import ConfidenceState, EvidenceClassification


@dataclass(frozen=True)
class SignalSnapshot:
    key: str
    present: bool
    classification: EvidenceClassification
    confidence_score: Decimal | None
    decision_eligible: bool
    explanation: str
    source_observation_id: UUID | None = None


@dataclass(frozen=True)
class FactorResult:
    key: str
    label: str
    max_points: Decimal
    raw_points: Decimal
    adjusted_points: Decimal
    matched_rule_keys: tuple[str, ...] = ()
    source_observation_id: UUID | None = None
    evidence_classification: EvidenceClassification = EvidenceClassification.DERIVED
    explanation: str = ""


@dataclass(frozen=True)
class ConfidenceComponentResult:
    key: str
    label: str
    weight: Decimal
    trust_fraction: Decimal
    weighted_points: Decimal
    explanation: str


@dataclass(frozen=True)
class ProductFitResult:
    product_code: str
    product_name: str
    raw_score: Decimal
    fit_score: Decimal
    fit_band: str
    classification: EvidenceClassification
    confidence_state: ConfidenceState
    explanation: str
    matched_signals: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    score_cap_applied: Decimal | None = None


@dataclass(frozen=True)
class CounterfactualResult:
    key: str
    label: str
    score: Decimal
    disposition: str
    score_delta: Decimal
    changes_disposition: bool
    excluded_factor_keys: tuple[str, ...] = ()
    excluded_rule_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionUnknown:
    key: str
    label: str
    impact_score: int
    impact_band: str
    validation: str


@dataclass(frozen=True)
class QualificationResult:
    project_id: UUID
    external_project_id: str | None
    model_version: str
    confidence_model_version: str
    product_registry_version: str
    commercial_fit_score: Decimal
    data_confidence_score: Decimal
    disposition: str
    operational_action: str
    confidence_state: ConfidenceState
    factors: tuple[FactorResult, ...]
    confidence_components: tuple[ConfidenceComponentResult, ...]
    product_fits: tuple[ProductFitResult, ...]
    signals: tuple[SignalSnapshot, ...]
    counterfactuals: tuple[CounterfactualResult, ...] = ()
    decision_changing_unknowns: tuple[DecisionUnknown, ...] = ()
    what_would_change_my_mind: tuple[CounterfactualResult, ...] = ()
    assessment_id: UUID | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
