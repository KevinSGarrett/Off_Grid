from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import ConfidenceState, VerificationState
from app.models import Project, ProjectOrganization, QualityFlag, SourceObservation
from app.scoring.config import LoadedConfig
from app.scoring.types import ConfidenceComponentResult, SignalSnapshot


def _d(value: object) -> Decimal:
    return Decimal(str(value))


class DataConfidenceEngine:
    def __init__(self, session: Session, config: LoadedConfig):
        self.session = session
        self.config = config.data

    def evaluate(
        self, project: Project, signals: dict[str, SignalSnapshot]
    ) -> tuple[Decimal, ConfidenceState, tuple[ConfidenceComponentResult, ...]]:
        observations = self.session.scalars(
            sa.select(SourceObservation).where(SourceObservation.project_id == project.id)
        ).all()
        by_field: dict[str, list[SourceObservation]] = {}
        for obs in observations:
            by_field.setdefault(obs.field_name, []).append(obs)

        validation_multipliers = {
            key: _d(value) for key, value in self.config.get("validation_multipliers", {}).items()
        }
        components: list[ConfidenceComponentResult] = []
        total = Decimal("0")

        for row in self.config.get("observation_components", []):
            field = str(row["field"])
            weight = _d(row["weight"])
            candidates = by_field.get(field, [])
            obs = max(candidates, key=lambda x: x.created_at) if candidates else None
            if obs is None:
                trust = Decimal("0")
                explanation = f"Required confidence input {field} is missing."
            else:
                base = _d(obs.confidence_score or 0)
                multiplier = validation_multipliers.get(obs.validation_state.value, Decimal("0.5"))
                trust = max(Decimal("0"), min(Decimal("1"), base * multiplier))
                explanation = (
                    f"{field}: source confidence {base:.2f}; validation {obs.validation_state.value}; "
                    f"scoring treatment {obs.scoring_treatment.value}."
                )
            weighted = weight * trust
            total += weighted
            components.append(
                ConfidenceComponentResult(
                    key=field,
                    label=str(row["label"]),
                    weight=weight,
                    trust_fraction=trust,
                    weighted_points=weighted,
                    explanation=explanation,
                )
            )

        for row in self.config.get("relationship_components", []):
            weight = _d(row["weight"])
            role = str(row["role"])
            relationships = self.session.scalars(
                sa.select(ProjectOrganization).where(
                    ProjectOrganization.project_id == project.id,
                    ProjectOrganization.role == role,
                )
            ).all()
            state = VerificationState.UNKNOWN
            if relationships:
                rank = {
                    VerificationState.REJECTED: 0,
                    VerificationState.CONFLICTED: 1,
                    VerificationState.UNKNOWN: 2,
                    VerificationState.SUPPORTED: 3,
                    VerificationState.VERIFIED: 4,
                }
                state = max((r.verification_state for r in relationships), key=lambda x: rank[x])
            trust = _d(row.get("state_scores", {}).get(state.value, 0))
            weighted = weight * trust
            total += weighted
            components.append(
                ConfidenceComponentResult(
                    key=str(row["key"]),
                    label=str(row["label"]),
                    weight=weight,
                    trust_fraction=trust,
                    weighted_points=weighted,
                    explanation=f"{role} relationship state: {state.value}.",
                )
            )

        for row in self.config.get("completeness_components", []):
            weight = _d(row["weight"])
            signal = signals.get(str(row["signal"]))
            present = bool(signal and signal.present)
            trust = _d(row["present_score"] if present else row["missing_score"])
            weighted = weight * trust
            total += weighted
            components.append(
                ConfidenceComponentResult(
                    key=str(row["key"]),
                    label=str(row["label"]),
                    weight=weight,
                    trust_fraction=trust,
                    weighted_points=weighted,
                    explanation=("Required completeness evidence is present." if present else "Required completeness evidence is missing/unknown."),
                )
            )

        penalties = self.config.get("quality_flag_penalties", {})
        flag_codes = {
            f.rule_code
            for f in self.session.scalars(
                sa.select(QualityFlag).where(QualityFlag.project_id == project.id)
            ).all()
        }
        penalty_total = sum((_d(penalties.get(code, 0)) for code in flag_codes), Decimal("0"))
        total = max(Decimal("0"), min(Decimal("100"), total - penalty_total))
        total = total.quantize(Decimal("0.01"))
        return total, self._state(total), tuple(components)

    def _state(self, score: Decimal) -> ConfidenceState:
        bands = self.config["model"]["bands"]
        for state_name in ("VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"):
            if score >= _d(bands[state_name]):
                return ConfidenceState(state_name)
        return ConfidenceState.VERY_LOW
