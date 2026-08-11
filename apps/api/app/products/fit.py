from __future__ import annotations

from decimal import Decimal

from app.domain.states import ConfidenceState, EvidenceClassification
from app.products.registry import ProductRegistry
from app.scoring.types import ProductFitResult, SignalSnapshot


def _d(value: object) -> Decimal:
    return Decimal(str(value))


def _band(score: Decimal) -> str:
    if score >= Decimal("80"):
        return "HIGH"
    if score >= Decimal("60"):
        return "MEDIUM_HIGH"
    if score >= Decimal("40"):
        return "MEDIUM"
    if score >= Decimal("20"):
        return "LOW"
    return "VERY_LOW"


class ProductFitEngine:
    """Evidence-constrained commercial product fit.

    The resulting recommendation is INFERRED even when every input signal is explicit. The engine
    never converts an application hypothesis into an approved product specification.
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
            score = Decimal("0")
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
            raw_score = min(Decimal("100"), score)

            gate = product.validation_gate
            gate_signals = [signals.get(str(key)) for key in gate.get("until_any_signal", [])]
            gate_satisfied = any(signal and signal.present for signal in gate_signals)
            cap = None
            if gate and not gate_satisfied:
                cap = _d(gate.get("cap_score", 100))
                score = min(score, cap)

            missing: list[str] = []
            for evidence in product.required_evidence:
                signal = signals.get(str(evidence["key"]))
                if not signal or not signal.present:
                    missing.append(str(evidence["label"]))

            fit_score = min(Decimal("100"), score).quantize(Decimal("0.01"))
            explanation = (
                f"{product.code} fit is a commercial inference from approved product facts plus "
                f"decision-eligible project signals ({', '.join(matched) if matched else 'none'})."
            )
            if cap is not None and raw_score > cap:
                explanation += f" Score capped at {cap} until direct use-case evidence is confirmed."
            results.append(
                ProductFitResult(
                    product_code=product.code,
                    product_name=product.name,
                    raw_score=raw_score.quantize(Decimal("0.01")),
                    fit_score=fit_score,
                    fit_band=_band(fit_score),
                    classification=EvidenceClassification.INFERRED,
                    confidence_state=data_confidence_state,
                    explanation=explanation,
                    matched_signals=tuple(matched),
                    missing_evidence=tuple(missing),
                    score_cap_applied=cap,
                )
            )
        return tuple(results)
