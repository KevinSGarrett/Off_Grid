from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import ConfidenceState, EvidenceClassification, ProjectState
from app.models import (
    AssessmentFactor,
    ConfigVersion,
    OpportunityAssessment,
    ProductFitAssessment,
    Project,
    ScoringConfig,
)
from app.products.fit import ProductFitEngine
from app.products.registry import ProductRegistry, load_product_registry
from app.scoring.config import LoadedConfig, load_confidence_config, load_qualification_config
from app.scoring.signals import ProjectSignalBuilder
from app.scoring.trust import DataConfidenceEngine
from app.scoring.types import (
    CounterfactualResult,
    DecisionUnknown,
    FactorResult,
    QualificationResult,
    SignalSnapshot,
)


def _d(value: object) -> Decimal:
    return Decimal(str(value))


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QualificationService:
    """Computed, configuration-versioned commercial qualification.

    No project name, external ID, or legacy illustrative score participates in the score. The same
    normalized facts + config produce the same result. Product fit is evaluated separately and is
    always labeled as commercial inference rather than product/source fact.
    """

    def __init__(
        self,
        session: Session,
        *,
        qualification_config: str | Path = "config/qualification.yaml",
        confidence_config: str | Path = "config/trust_confidence.yaml",
        product_config: str | Path = "config/products.yaml",
    ) -> None:
        self.session = session
        self.qualification: LoadedConfig = load_qualification_config(qualification_config)
        self.confidence: LoadedConfig = load_confidence_config(confidence_config)
        self.products: ProductRegistry = load_product_registry(product_config)

    def evaluate_by_external_id(self, external_id: str, *, persist: bool = True) -> QualificationResult:
        project = self.session.scalar(
            sa.select(Project).where(Project.source_system == "constructconnect", Project.external_id == external_id)
        )
        if project is None:
            raise LookupError(f"Project not found for external id {external_id}")
        return self.evaluate(project.id, persist=persist)

    def evaluate(self, project_id: UUID, *, persist: bool = True) -> QualificationResult:
        project = self.session.get(Project, project_id)
        if project is None:
            raise LookupError(f"Project not found: {project_id}")

        signals = ProjectSignalBuilder(self.session).build(project, persist=persist)
        data_confidence_score, confidence_state, confidence_components = DataConfidenceEngine(
            self.session, self.confidence
        ).evaluate(project, signals)
        factors, score = self._score(signals)
        disposition = self._disposition(score)
        action = self._action(score, data_confidence_score)
        product_fits = ProductFitEngine(self.products).evaluate(
            signals, data_confidence_state=confidence_state
        )
        counterfactuals = self._counterfactuals(signals, score, disposition)
        unknowns = self._unknowns(signals)
        changing = tuple(
            sorted(
                (item for item in counterfactuals if item.changes_disposition),
                key=lambda item: (item.score, item.key),
            )
        )

        assessment_id = None
        if persist:
            assessment_id = self._persist(
                project=project,
                factors=factors,
                commercial_fit_score=score,
                data_confidence_score=data_confidence_score,
                confidence_state=confidence_state,
                disposition=disposition,
                product_fits=product_fits,
            )
            project.state = ProjectState.QUALIFIED
            self.session.commit()

        return QualificationResult(
            project_id=project.id,
            external_project_id=project.external_id,
            model_version=str(self.qualification.data["model"]["version"]),
            confidence_model_version=str(self.confidence.data["model"]["version"]),
            product_registry_version=self.products.version,
            commercial_fit_score=score,
            data_confidence_score=data_confidence_score,
            disposition=disposition,
            operational_action=action,
            confidence_state=confidence_state,
            factors=factors,
            confidence_components=confidence_components,
            product_fits=product_fits,
            signals=tuple(sorted(signals.values(), key=lambda item: item.key)),
            counterfactuals=counterfactuals,
            decision_changing_unknowns=unknowns,
            what_would_change_my_mind=changing,
            assessment_id=assessment_id,
            notes=(
                "Commercial Fit is separate from Data Confidence.",
                "INFERRED/UNKNOWN signals are not eligible for deterministic qualification.",
                "Reported project value is limited to its configured rule contribution and source CAPPED treatment.",
            ),
        )

    def _score(
        self,
        signals: dict[str, SignalSnapshot],
        *,
        excluded_factor_keys: set[str] | None = None,
        excluded_rule_keys: set[str] | None = None,
    ) -> tuple[tuple[FactorResult, ...], Decimal]:
        excluded_factor_keys = excluded_factor_keys or set()
        excluded_rule_keys = excluded_rule_keys or set()
        factor_results: list[FactorResult] = []
        total = Decimal("0")

        for factor in self.qualification.data["factors"]:
            fkey = str(factor["key"])
            max_points = _d(factor["max_points"])
            if fkey in excluded_factor_keys:
                factor_results.append(
                    FactorResult(
                        key=fkey,
                        label=str(factor["label"]),
                        max_points=max_points,
                        raw_points=Decimal("0"),
                        adjusted_points=Decimal("0"),
                        explanation="Counterfactual exclusion: entire factor removed.",
                    )
                )
                continue

            raw = Decimal("0")
            matched: list[str] = []
            source_ids: list[UUID] = []
            classes: list[EvidenceClassification] = []
            explanations: list[str] = []
            for rule in factor.get("rules", []):
                rkey = str(rule["key"])
                if rkey in excluded_rule_keys:
                    continue
                signal = signals.get(str(rule["signal"]))
                if not signal or not signal.present or not signal.decision_eligible:
                    continue
                if signal.classification not in {
                    EvidenceClassification.EXPLICIT,
                    EvidenceClassification.DERIVED,
                    EvidenceClassification.VERIFIED,
                }:
                    continue
                raw += _d(rule["points"])
                matched.append(rkey)
                if signal.source_observation_id:
                    source_ids.append(signal.source_observation_id)
                classes.append(signal.classification)
                explanations.append(f"{rkey}: {signal.explanation}")

            adjusted = min(max_points, raw)
            total += adjusted
            factor_results.append(
                FactorResult(
                    key=fkey,
                    label=str(factor["label"]),
                    max_points=max_points,
                    raw_points=raw,
                    adjusted_points=adjusted,
                    matched_rule_keys=tuple(matched),
                    source_observation_id=source_ids[0] if source_ids else None,
                    evidence_classification=(
                        EvidenceClassification.DERIVED
                        if EvidenceClassification.DERIVED in classes
                        else EvidenceClassification.EXPLICIT
                    ),
                    explanation=" | ".join(explanations) if explanations else "No eligible evidence matched this factor.",
                )
            )

        score = max(Decimal("0"), min(Decimal("100"), total)).quantize(Decimal("0.01"))
        return tuple(factor_results), score

    def _disposition(self, score: Decimal) -> str:
        thresholds = self.qualification.data["model"]["thresholds"]
        if score >= _d(thresholds["pursue"]):
            return "PURSUE"
        if score >= _d(thresholds["review"]):
            return "REVIEW"
        return "PASS"

    def _fit_band(self, score: Decimal) -> str:
        thresholds = self.qualification.data["model"]["thresholds"]
        if score >= _d(thresholds["pursue"]):
            return "HIGH"
        if score >= _d(thresholds["review"]):
            return "MEDIUM"
        return "LOW"

    def _confidence_band(self, score: Decimal) -> str:
        bands = self.qualification.data["model"]["confidence_bands"]
        if score >= _d(bands["high"]):
            return "HIGH"
        if score >= _d(bands["medium"]):
            return "MEDIUM"
        return "LOW"

    def _action(self, fit_score: Decimal, confidence_score: Decimal) -> str:
        fit = self._fit_band(fit_score)
        confidence = self._confidence_band(confidence_score)
        return str(self.qualification.data["model"]["fit_confidence_matrix"][fit][confidence])

    def _counterfactuals(
        self,
        signals: dict[str, SignalSnapshot],
        baseline_score: Decimal,
        baseline_disposition: str,
    ) -> tuple[CounterfactualResult, ...]:
        rows: list[CounterfactualResult] = []

        _, score = self._score(signals, excluded_rule_keys={"large_project_value"})
        disposition = self._disposition(score)
        rows.append(
            CounterfactualResult(
                key="ignore_reported_value",
                label="Ignore the reported project value entirely",
                score=score,
                disposition=disposition,
                score_delta=(score - baseline_score).quantize(Decimal("0.01")),
                changes_disposition=disposition != baseline_disposition,
                excluded_rule_keys=("large_project_value",),
            )
        )

        for factor in self.qualification.data["factors"]:
            fkey = str(factor["key"])
            _, score = self._score(signals, excluded_factor_keys={fkey})
            disposition = self._disposition(score)
            rows.append(
                CounterfactualResult(
                    key=f"without_{fkey}",
                    label=str(factor.get("counterfactual_label") or f"Remove {factor['label']}") ,
                    score=score,
                    disposition=disposition,
                    score_delta=(score - baseline_score).quantize(Decimal("0.01")),
                    changes_disposition=disposition != baseline_disposition,
                    excluded_factor_keys=(fkey,),
                )
            )
        return tuple(rows)

    def _unknowns(self, signals: dict[str, SignalSnapshot]) -> tuple[DecisionUnknown, ...]:
        result: list[DecisionUnknown] = []
        for row in self.qualification.data.get("unknowns", []):
            trigger = str(row.get("trigger_signal_absent", ""))
            signal = signals.get(trigger)
            if signal is not None and signal.present:
                continue
            impact = int(row["impact_score"])
            if impact >= 90:
                band = "VERY_HIGH"
            elif impact >= 75:
                band = "HIGH"
            elif impact >= 50:
                band = "MEDIUM"
            else:
                band = "LOW"
            result.append(
                DecisionUnknown(
                    key=str(row["key"]),
                    label=str(row["label"]),
                    impact_score=impact,
                    impact_band=band,
                    validation=str(row["validation"]),
                )
            )
        return tuple(sorted(result, key=lambda item: (-item.impact_score, item.key)))

    def _ensure_config_version(self, kind: str, loaded: LoadedConfig, version: str) -> ConfigVersion:
        existing = self.session.scalar(
            sa.select(ConfigVersion).where(
                ConfigVersion.config_kind == kind,
                ConfigVersion.version == version,
            )
        )
        if existing is not None:
            if existing.content_sha256 != loaded.sha256:
                raise ValueError(f"Config version {kind}:{version} changed content without a version bump")
            return existing
        self.session.execute(
            sa.update(ConfigVersion).where(ConfigVersion.config_kind == kind).values(is_active=False)
        )
        row = ConfigVersion(
            config_kind=kind,
            version=version,
            content_sha256=loaded.sha256,
            source_path=str(loaded.path.relative_to(Path(__file__).resolve().parents[4])),
            content_text=loaded.text,
            activated_at=_now(),
            is_active=True,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _persist(
        self,
        *,
        project: Project,
        factors: tuple[FactorResult, ...],
        commercial_fit_score: Decimal,
        data_confidence_score: Decimal,
        confidence_state: ConfidenceState,
        disposition: str,
        product_fits,
    ) -> UUID:
        q_version = str(self.qualification.data["model"]["version"])
        q_cfg = self._ensure_config_version("qualification", self.qualification, q_version)
        self._ensure_config_version("confidence", self.confidence, str(self.confidence.data["model"]["version"]))
        self._ensure_config_version("products", self.products.loaded, self.products.version)

        scoring = self.session.scalar(
            sa.select(ScoringConfig).where(
                ScoringConfig.config_version_id == q_cfg.id,
                ScoringConfig.model_name == str(self.qualification.data["model"]["name"]),
            )
        )
        if scoring is None:
            thresholds = self.qualification.data["model"]["thresholds"]
            scoring = ScoringConfig(
                config_version_id=q_cfg.id,
                model_name=str(self.qualification.data["model"]["name"]),
                model_version=q_version,
                pursue_threshold=float(thresholds["pursue"]),
                review_threshold=float(thresholds["review"]),
                notes="Wave 6 deterministic config-driven qualification.",
            )
            self.session.add(scoring)
            self.session.flush()

        self.session.execute(
            sa.update(OpportunityAssessment)
            .where(OpportunityAssessment.project_id == project.id, OpportunityAssessment.is_current.is_(True))
            .values(is_current=False)
        )
        assessment = OpportunityAssessment(
            project_id=project.id,
            scoring_config_id=scoring.id,
            commercial_fit_score=commercial_fit_score,
            data_confidence_score=data_confidence_score,
            disposition=disposition,
            confidence_state=confidence_state,
            computed_at=_now(),
            explanation="Computed from decision-eligible normalized evidence; fit and confidence are intentionally separate.",
            is_current=True,
        )
        self.session.add(assessment)
        self.session.flush()

        for factor in factors:
            self.session.add(
                AssessmentFactor(
                    assessment_id=assessment.id,
                    factor_key=factor.key,
                    label=factor.label,
                    weight=factor.max_points,
                    raw_points=factor.raw_points,
                    adjusted_points=factor.adjusted_points,
                    cap_points=factor.max_points,
                    source_observation_id=factor.source_observation_id,
                    evidence_classification=factor.evidence_classification,
                    explanation=factor.explanation,
                )
            )
        for fit in product_fits:
            self.session.add(
                ProductFitAssessment(
                    opportunity_assessment_id=assessment.id,
                    product_code=fit.product_code,
                    fit_score=fit.fit_score,
                    fit_band=fit.fit_band,
                    classification=fit.classification,
                    confidence_state=fit.confidence_state,
                    explanation=fit.explanation,
                    missing_evidence="\n".join(fit.missing_evidence),
                )
            )
        self.session.flush()
        return assessment.id
