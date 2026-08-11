from __future__ import annotations

from collections.abc import Collection

from app.domain.states import AIClaimStatus, EvidenceClassification, ValidationState
from app.domain.errors import EvidenceGroundingError


AI_PERMITTED_CLASSIFICATIONS = {
    EvidenceClassification.DERIVED,
    EvidenceClassification.INFERRED,
    EvidenceClassification.CONFLICTED,
    EvidenceClassification.UNKNOWN,
}


def validate_ai_claim_grounding(
    *,
    classification: EvidenceClassification,
    evidence_ids: Collection[object],
    existing_evidence_ids: Collection[object],
) -> tuple[ValidationState, AIClaimStatus]:
    """Validate the minimum provenance rules for an AI-produced claim.

    AI output cannot self-declare EXPLICIT or VERIFIED. Every referenced evidence identifier must
    already exist in the evidence store. A claim with no cited evidence can remain proposed/unknown
    but cannot be accepted as grounded commercial truth.
    """
    if classification not in AI_PERMITTED_CLASSIFICATIONS:
        raise EvidenceGroundingError(
            f"AI cannot promote its own output to {classification.value}; verification must come "
            "from source/independent evidence."
        )
    missing = set(evidence_ids) - set(existing_evidence_ids)
    if missing:
        raise EvidenceGroundingError(f"AI claim references unknown evidence ids: {sorted(map(str, missing))}")
    if not evidence_ids:
        return ValidationState.REQUIRES_REVIEW, AIClaimStatus.PROPOSED
    return ValidationState.VALID, AIClaimStatus.GROUNDED


def may_promote_observation(
    *, classification: EvidenceClassification, validation_state: ValidationState
) -> bool:
    """Whether an observation may influence deterministic decision logic without human review."""
    if validation_state != ValidationState.VALID:
        return False
    return classification in {
        EvidenceClassification.EXPLICIT,
        EvidenceClassification.DERIVED,
        EvidenceClassification.VERIFIED,
    }


def observation_decision_eligibility(
    *,
    classification: EvidenceClassification,
    validation_state: ValidationState,
    scoring_treatment,
) -> tuple[bool, str]:
    """Return whether a normalized observation may affect deterministic qualification.

    CAPPED source-explicit/derived/verified observations may contribute only through an explicit
    configured cap even when they require review. REVIEW/EXCLUDED observations cannot contribute.
    Inferred/unknown/conflicted claims cannot become deterministic inputs merely because they exist.
    """
    from app.domain.states import ScoringTreatment

    if classification not in {
        EvidenceClassification.EXPLICIT,
        EvidenceClassification.DERIVED,
        EvidenceClassification.VERIFIED,
    }:
        return False, f"{classification.value} evidence is not eligible for deterministic qualification."
    if validation_state in {ValidationState.INVALID, ValidationState.CONFLICTED, ValidationState.QUARANTINED}:
        return False, f"Validation state {validation_state.value} blocks deterministic qualification."
    if scoring_treatment in {ScoringTreatment.EXCLUDED, ScoringTreatment.REVIEW}:
        return False, f"Scoring treatment {scoring_treatment.value} requires exclusion/review."
    if scoring_treatment is ScoringTreatment.CAPPED:
        return True, "Permitted only through an explicit configured cap; source uncertainty remains visible."
    if validation_state is not ValidationState.VALID:
        return False, f"Validation state {validation_state.value} is not fully valid for FULL scoring."
    return True, "Validated source/derived evidence is permitted for deterministic qualification."
