from __future__ import annotations

from decimal import Decimal

from app.domain.states import ConfidenceState, EvidenceClassification
from app.products.registry import ProductRegistry
from app.scoring.types import ProductFitResult, SignalSnapshot


def _d(value: object) -> Decimal:
    return Decimal(str(value))


class ProductFitEngine:
    """Evidence-constrained product applicability and characteristic relevance.

    The numeric result is a deterministic project-characteristic ordering index, while the
    applicability status is independently gated by direct need and product-specific evidence.
    The engine never converts an application hypothesis into approved demand or a specification.
    """

    def __init__(self, registry: ProductRegistry):
        self.registry = registry

    def evaluate(
        self,
        signals: dict[str, SignalSnapshot],
        *,
        data_confidence_state: ConfidenceState,
    ) -> tuple[ProductFitResult, ...]:
        results: list[ProductFitResult] = []
        for product in self.registry.products:
            score = Decimal(0)
            matched: list[str] = []
            for rule in product.fit_rules:
                signal = signals.get(str(rule["signal"]))
                if signal and signal.present and signal.decision_eligible and signal.classification in {
                    EvidenceClassification.EXPLICIT,
                    EvidenceClassification.DERIVED,
                    EvidenceClassification.VERIFIED,
                }:
                    score += _d(rule["points"])
                    matched.append(signal.key)
            raw_score = min(Decimal(100), score)

            gate = product.validation_gate

            def any_present(keys: list[str]) -> bool:
                return any(signals.get(str(key)) and signals[str(key)].present for key in keys)

            context_present = any_present(list(gate.get("context_signals", [])))
            need_present = any_present(list(gate.get("need_signals", [])))
            confirmation_present = any_present(list(gate.get("confirmation_signals", [])))
            cap = None

            missing: list[str] = []
            for evidence in product.required_evidence:
                signal = signals.get(str(evidence["key"]))
                if not signal or not signal.present:
                    missing.append(str(evidence["label"]))

            fit_score = min(Decimal(100), score).quantize(Decimal("0.01"))
            if need_present and confirmation_present:
                status = str(gate.get("validated_status", "CONFIRMED_FIT"))
            elif need_present:
                status = str(gate.get("confirmed_status", "SUPPORTED_CANDIDATE"))
            elif context_present:
                status = str(gate.get("unconfirmed_status", "UNVERIFIED_APPLICABILITY"))
            else:
                status = str(gate.get("not_indicated_status", "NOT_INDICATED"))
            explanation = (
                f"{product.code} project characteristics suggest possible relevance from "
                f"decision-eligible context ({', '.join(matched) if matched else 'none'}). "
                "This is not verified demand or a validated product specification."
            )
            if not need_present:
                explanation += " Applicability remains unverified until direct lighting/power need is confirmed."
            results.append(
                ProductFitResult(
                    product_code=product.code,
                    product_name=product.name,
                    raw_score=raw_score.quantize(Decimal("0.01")),
                    fit_score=fit_score,
                    fit_band=status,
                    classification=EvidenceClassification.INFERRED,
                    confidence_state=data_confidence_state,
                    explanation=explanation,
                    matched_signals=tuple(matched),
                    missing_evidence=tuple(missing),
                    score_cap_applied=cap,
                    applicability_status=status,
                    supporting_evidence=tuple(matched),
                    contradicting_evidence=(),
                )
            )
        return tuple(results)
