from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
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
    ComparisonCohortResult,
    CounterfactualResult,
    DecisionUnknown,
    DimensionResult,
    FactorResult,
    QualificationResult,
    SignalSnapshot,
)


def _d(value: object) -> Decimal:
    return Decimal(str(value))


def _now() -> datetime:
    return datetime.now(UTC)


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
        factors, dimensions, score = self._score(signals)
        band = self._band(score)
        action = self._action(band, dimensions, data_confidence_score)
        disposition = action
        product_fits = ProductFitEngine(self.products).evaluate(
            signals, data_confidence_state=confidence_state
        )
        counterfactuals = self._counterfactuals(signals, score, band, action, data_confidence_score)
        unknowns = self._unknowns(signals)
        comparison = self._comparison_cohorts(project)
        changing = tuple(
            sorted(
                (item for item in counterfactuals if item.changes_band or item.changes_action),
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
            overall_band=band,
            confidence_state=confidence_state,
            factors=factors,
            dimensions=dimensions
            + (
                DimensionResult(
                    key="evidence_reliability",
                    label="Evidence reliability and completeness",
                    internal_score=data_confidence_score,
                    max_points=Decimal(100),
                    band=confidence_state.value,
                    supporting_evidence=tuple(
                        item.explanation for item in confidence_components if item.trust_fraction > 0
                    ),
                    missing_evidence=tuple(
                        item.explanation for item in confidence_components if item.trust_fraction < 1
                    ),
                ),
            ),
            confidence_components=confidence_components,
            product_fits=product_fits,
            signals=tuple(sorted(signals.values(), key=lambda item: item.key)),
            counterfactuals=counterfactuals,
            decision_changing_unknowns=unknowns,
            what_would_change_my_mind=changing,
            comparison_cohorts=comparison,
            assessment_id=assessment_id,
            notes=(
                "Commercial Fit is separate from Data Confidence.",
                "INFERRED/UNKNOWN signals are not eligible for deterministic qualification.",
                "Internal scores support deterministic ordering only; bands/actions are not probabilities or forecasts.",
                "Reported project value contributes zero qualification points and remains source-caveated.",
                "Product characteristics indicate possible relevance only; direct product need remains unverified.",
            ),
        )

    def _score(
        self,
        signals: dict[str, SignalSnapshot],
        *,
        excluded_factor_keys: set[str] | None = None,
        excluded_rule_keys: set[str] | None = None,
    ) -> tuple[tuple[FactorResult, ...], tuple[DimensionResult, ...], Decimal]:
        excluded_factor_keys = excluded_factor_keys or set()
        excluded_rule_keys = excluded_rule_keys or set()
        factor_results: list[FactorResult] = []
        dimension_results: list[DimensionResult] = []
        total = Decimal(0)

        for factor in self.qualification.data["dimensions"]:
            fkey = str(factor["key"])
            max_points = _d(factor["max_points"])
            if fkey in excluded_factor_keys:
                factor_results.append(
                    FactorResult(
                        key=fkey,
                        label=str(factor["label"]),
                        max_points=max_points,
                        raw_points=Decimal(0),
                        adjusted_points=Decimal(0),
                        explanation="Counterfactual exclusion: entire factor removed.",
                    )
                )
                dimension_results.append(
                    DimensionResult(
                        key=fkey,
                        label=str(factor["label"]),
                        internal_score=Decimal(0),
                        max_points=max_points,
                        band="NOT_ASSESSED",
                        missing_evidence=("Counterfactual exclusion",),
                    )
                )
                continue

            raw = Decimal(0)
            matched: list[str] = []
            source_ids: list[UUID] = []
            classes: list[EvidenceClassification] = []
            explanations: list[str] = []
            supports: list[str] = []
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
                supports.append(signal.explanation)

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
            missing = tuple(
                str(item["label"])
                for item in factor.get("missing_when_absent", [])
                if not (
                    (candidate := signals.get(str(item["signal"])))
                    and candidate.present
                    and candidate.decision_eligible
                )
            )
            dimension_results.append(
                DimensionResult(
                    key=fkey,
                    label=str(factor["label"]),
                    internal_score=adjusted,
                    max_points=max_points,
                    band=self._dimension_band(adjusted, max_points),
                    supporting_evidence=tuple(supports),
                    contradicting_evidence=(),
                    missing_evidence=missing,
                    matched_signal_keys=tuple(
                        str(rule["signal"])
                        for rule in factor.get("rules", [])
                        if str(rule["key"]) in matched
                    ),
                )
            )

        score = max(Decimal(0), min(Decimal(100), total)).quantize(Decimal("0.01"))
        return tuple(factor_results), tuple(dimension_results), score

    def _band(self, score: Decimal) -> str:
        bands = self.qualification.data["model"]["bands"]
        if score >= _d(bands["strong_candidate"]):
            return "Strong candidate"
        if score >= _d(bands["promising_candidate"]):
            return "Promising candidate"
        if score >= _d(bands["needs_investigation"]):
            return "Needs investigation"
        return "Weak / not indicated"

    @staticmethod
    def _dimension_band(score: Decimal, maximum: Decimal) -> str:
        fraction = score / maximum if maximum else Decimal(0)
        if fraction >= Decimal("0.75"):
            return "STRONG"
        if fraction >= Decimal("0.45"):
            return "PARTIAL"
        if score > 0:
            return "LIMITED"
        return "NOT_CONFIRMED"

    @staticmethod
    def _action(
        band: str,
        dimensions: tuple[DimensionResult, ...],
        confidence_score: Decimal,
    ) -> str:
        by_key = {item.key: item for item in dimensions}
        need = by_key["confirmed_product_need"].internal_score
        access = by_key["account_access"].internal_score
        if band == "Strong candidate" and need >= 15 and access >= 12 and confidence_score >= 65:
            return "ACT"
        if band in {"Strong candidate", "Promising candidate"}:
            return "VERIFY"
        if band == "Needs investigation":
            return "REVIEW"
        return "PASS"

    def _counterfactuals(
        self,
        signals: dict[str, SignalSnapshot],
        baseline_score: Decimal,
        baseline_band: str,
        baseline_action: str,
        confidence_score: Decimal,
    ) -> tuple[CounterfactualResult, ...]:
        rows: list[CounterfactualResult] = []

        for row in self.qualification.data.get("counterfactuals", []):
            changed = dict(signals)
            for key in row.get("set_absent", []):
                if key in changed:
                    changed[key] = replace(changed[key], present=False, decision_eligible=False)
            for key in row.get("set_present", []):
                current = changed.get(key)
                if current is not None:
                    changed[key] = replace(
                        current,
                        present=True,
                        decision_eligible=True,
                        classification=EvidenceClassification.VERIFIED,
                        confidence_score=Decimal(1),
                        explanation=f"Counterfactual only: {row['label']}",
                    )
            _, dimensions, score = self._score(changed)
            band = self._band(score)
            action = self._action(band, dimensions, confidence_score)
            rows.append(
                CounterfactualResult(
                    key=str(row["key"]),
                    label=str(row["label"]),
                    score=score,
                    disposition=action,
                    score_delta=(score - baseline_score).quantize(Decimal("0.01")),
                    changes_disposition=band != baseline_band,
                    band=band,
                    action=action,
                    changes_band=band != baseline_band,
                    changes_action=action != baseline_action,
                )
            )
        return tuple(rows)

    def _unknowns(self, signals: dict[str, SignalSnapshot]) -> tuple[DecisionUnknown, ...]:
        result: list[DecisionUnknown] = []
        config = self.qualification.data.get("next_information", {})
        method = config.get("method", {})
        for row in config.get("items", []):
            trigger = str(row.get("trigger_signal_absent", ""))
            signal = signals.get(trigger)
            if signal is not None and signal.present:
                continue
            decision_impact = int(row["decision_impact"])
            evidence_gap = int(row["evidence_gap"])
            resolvability = int(row["resolvability"])
            impact = round(decision_impact * 12.5 + evidence_gap * 10 + resolvability * 6.25)
            if impact >= 100:
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
                    decision_impact=decision_impact,
                    evidence_gap=evidence_gap,
                    resolvability=resolvability,
                    method_version=str(method.get("version", "value-of-next-information-1.0")),
                )
            )
        return tuple(sorted(result, key=lambda item: (-item.impact_score, item.key)))

    def _comparison_cohorts(self, project: Project) -> tuple[ComparisonCohortResult, ...]:
        projects = self.session.scalars(
            sa.select(Project).where(Project.is_synthetic.is_(False)).order_by(Project.id)
        ).all()
        total = len(projects)
        results: list[ComparisonCohortResult] = []
        for field in self.qualification.data.get("comparison", {}).get("fields", []):
            key = str(field["key"])
            values = [
                (row, getattr(row, key))
                for row in projects
                if getattr(row, key) is not None
                and (key != "reported_value" or row.currency_code == project.currency_code)
            ]
            coverage = (Decimal(len(values)) / Decimal(total)).quantize(Decimal("0.0001")) if total else Decimal(0)
            eligible = (
                getattr(project, key) is not None
                and coverage >= _d(field.get("minimum_coverage_fraction", 1))
            )
            rank = None
            percentile = None
            if eligible:
                current = getattr(project, key)
                higher = sum(1 for _, value in values if value > current)
                lower = sum(1 for _, value in values if value < current)
                rank = higher + 1
                percentile = (
                    Decimal(100) * Decimal(lower) / Decimal(len(values))
                ).quantize(Decimal("0.1"))
            results.append(
                ComparisonCohortResult(
                    field=key,
                    label=str(field["label"]),
                    eligible=eligible,
                    total_projects=total,
                    cohort_size=len(values),
                    field_coverage_fraction=coverage,
                    missing_count=total - len(values),
                    missing_data_treatment="Excluded from this field-specific cohort; never imputed as zero.",
                    rank=rank,
                    percentile=percentile,
                    direction=str(field.get("direction", "descending")),
                    caveat=str(field.get("note", "Comparable source fields only.")),
                )
            )
        return tuple(results)

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
            bands = self.qualification.data["model"]["bands"]
            scoring = ScoringConfig(
                config_version_id=q_cfg.id,
                model_name=str(self.qualification.data["model"]["name"]),
                model_version=q_version,
                pursue_threshold=float(bands["strong_candidate"]),
                review_threshold=float(bands["promising_candidate"]),
                notes="Qualification 2.0 deterministic, non-duplicative decision-support bands.",
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
