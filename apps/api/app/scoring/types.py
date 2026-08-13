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
class DimensionResult:
    key: str
    label: str
    internal_score: Decimal
    max_points: Decimal
    band: str
    supporting_evidence: tuple[str, ...] = ()
    contradicting_evidence: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    matched_signal_keys: tuple[str, ...] = ()


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
    applicability_status: str = "UNVERIFIED_APPLICABILITY"
    supporting_evidence: tuple[str, ...] = ()
    contradicting_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class CounterfactualResult:
    key: str
    label: str
    score: Decimal
    disposition: str
    score_delta: Decimal
    changes_disposition: bool
    band: str = ""
    action: str = ""
    changes_band: bool = False
    changes_action: bool = False
    excluded_factor_keys: tuple[str, ...] = ()
    excluded_rule_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionUnknown:
    key: str
    label: str
    impact_score: int
    impact_band: str
    validation: str
    decision_impact: int = 0
    evidence_gap: int = 0
    resolvability: int = 0
    method_version: str = "value-of-next-information-1.0"


@dataclass(frozen=True)
class ComparisonCohortResult:
    field: str
    label: str
    eligible: bool
    total_projects: int
    cohort_size: int
    field_coverage_fraction: Decimal
    missing_count: int
    missing_data_treatment: str
    rank: int | None
    percentile: Decimal | None
    direction: str
    caveat: str


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
    overall_band: str
    confidence_state: ConfidenceState
    factors: tuple[FactorResult, ...]
    dimensions: tuple[DimensionResult, ...]
    confidence_components: tuple[ConfidenceComponentResult, ...]
    product_fits: tuple[ProductFitResult, ...]
    signals: tuple[SignalSnapshot, ...]
    counterfactuals: tuple[CounterfactualResult, ...] = ()
    decision_changing_unknowns: tuple[DecisionUnknown, ...] = ()
    what_would_change_my_mind: tuple[CounterfactualResult, ...] = ()
    comparison_cohorts: tuple[ComparisonCohortResult, ...] = ()
    assessment_id: UUID | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
