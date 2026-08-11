from __future__ import annotations

import pytest

from app.domain.errors import EvidenceGroundingError
from app.domain.states import AIClaimStatus, EvidenceClassification, ValidationState
from app.services.provenance_policy import may_promote_observation, validate_ai_claim_grounding


def test_ai_cannot_self_declare_explicit_or_verified_fact() -> None:
    for classification in (EvidenceClassification.EXPLICIT, EvidenceClassification.VERIFIED):
        with pytest.raises(EvidenceGroundingError):
            validate_ai_claim_grounding(
                classification=classification,
                evidence_ids={"ev-1"},
                existing_evidence_ids={"ev-1"},
            )


def test_ai_claim_with_unknown_evidence_id_is_rejected() -> None:
    with pytest.raises(EvidenceGroundingError, match="unknown evidence ids"):
        validate_ai_claim_grounding(
            classification=EvidenceClassification.INFERRED,
            evidence_ids={"ev-missing"},
            existing_evidence_ids={"ev-1"},
        )


def test_ai_claim_without_evidence_remains_proposed_for_review() -> None:
    validation, status = validate_ai_claim_grounding(
        classification=EvidenceClassification.UNKNOWN,
        evidence_ids=set(),
        existing_evidence_ids={"ev-1"},
    )
    assert validation is ValidationState.REQUIRES_REVIEW
    assert status is AIClaimStatus.PROPOSED


def test_evidence_backed_inference_can_be_grounded_but_not_auto_promoted() -> None:
    validation, status = validate_ai_claim_grounding(
        classification=EvidenceClassification.INFERRED,
        evidence_ids={"ev-1"},
        existing_evidence_ids={"ev-1"},
    )
    assert validation is ValidationState.VALID
    assert status is AIClaimStatus.GROUNDED
    assert not may_promote_observation(
        classification=EvidenceClassification.INFERRED,
        validation_state=ValidationState.VALID,
    )


def test_only_valid_explicit_derived_or_verified_observation_auto_promotes() -> None:
    for classification in (
        EvidenceClassification.EXPLICIT,
        EvidenceClassification.DERIVED,
        EvidenceClassification.VERIFIED,
    ):
        assert may_promote_observation(
            classification=classification,
            validation_state=ValidationState.VALID,
        )
    assert not may_promote_observation(
        classification=EvidenceClassification.EXPLICIT,
        validation_state=ValidationState.REQUIRES_REVIEW,
    )
