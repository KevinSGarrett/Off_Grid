from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import EvidenceClassification, ProjectState
from app.ingestion.service import ConstructConnectIngestionService
from app.models import (
    AssessmentFactor,
    Base,
    ConfigVersion,
    OpportunityAssessment,
    ProductFitAssessment,
    Project,
)
from app.persistence.database import build_engine
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EXPECTED = json.loads((ROOT / "tests/golden/stafford_wave06_expected.json").read_text(encoding="utf-8"))


def _session() -> Session:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _ingest_and_score(session: Session, *, persist: bool = True):
    ConstructConnectIngestionService(session).ingest(STAFFORD)
    project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    result = QualificationService(session).evaluate(project.id, persist=persist)
    return project, result


def test_stafford_score_is_computed_reproducible_and_separate_from_confidence() -> None:
    with _session() as session:
        project, first = _ingest_and_score(session, persist=False)
        second = QualificationService(session).evaluate(project.id, persist=False)
        assert first.commercial_fit_score == second.commercial_fit_score
        assert first.data_confidence_score == second.data_confidence_score
        assert first.commercial_fit_score == sum(f.adjusted_points for f in first.factors)
        assert DecimalLike(first.commercial_fit_score).between(0, 100)
        assert DecimalLike(first.data_confidence_score).between(0, 100)
        assert first.model_version == EXPECTED["qualification_model_version"]
        assert first.commercial_fit_score == EXPECTED["stafford_internal_ordering_score"]
        assert first.overall_band == EXPECTED["stafford_band"]
        assert first.operational_action == EXPECTED["stafford_action"]
        assert first.confidence_model_version == EXPECTED["confidence_model_version"]
        # Distinct measures, not one shared opaque value.
        assert first.commercial_fit_score != first.data_confidence_score


def test_reported_value_has_zero_influence_and_counterfactual_preserves_decision() -> None:
    with _session() as session:
        _, result = _ingest_and_score(session, persist=False)
        counterfactual = next(x for x in result.counterfactuals if x.key == "without_reported_value")
        assert counterfactual.score_delta == EXPECTED["reported_value_max_points"]
        assert counterfactual.disposition == result.disposition
        assert all("large_project_value" not in factor.matched_rule_keys for factor in result.factors)


def test_source_fact_derived_and_inference_boundaries_are_visible() -> None:
    with _session() as session:
        _, result = _ingest_and_score(session, persist=False)
        signals = {x.key: x for x in result.signals}
        for key in EXPECTED["required_explicit_signals"]:
            assert signals[key].classification is EvidenceClassification.EXPLICIT
            assert signals[key].decision_eligible is True
        for key in EXPECTED["required_inferred_non_decision_signals"]:
            assert signals[key].classification is EvidenceClassification.INFERRED
            assert signals[key].decision_eligible is False


def test_product_fit_is_separate_inferred_and_missing_evidence_is_explicit() -> None:
    with _session() as session:
        _, result = _ingest_and_score(session, persist=False)
        fits = {x.product_code: x for x in result.product_fits}
        assert set(fits) == set(EXPECTED["required_products"])
        for fit in fits.values():
            assert fit.classification is EvidenceClassification.INFERRED
            assert fit.missing_evidence
            assert 0 <= fit.fit_score <= 100
            assert fit.applicability_status == "UNVERIFIED_APPLICABILITY"
        assert {fit.fit_band for fit in fits.values()} == {"UNVERIFIED_APPLICABILITY"}


def test_decision_unknowns_rank_material_questions_above_exact_phase_value() -> None:
    with _session() as session:
        _, result = _ingest_and_score(session, persist=False)
        unknowns = {x.key: x for x in result.decision_changing_unknowns}
        exact = unknowns[EXPECTED["required_low_impact_unknown"]]
        assert exact.impact_band == "LOW"
        for key in EXPECTED["required_high_impact_unknowns"]:
            assert unknowns[key].impact_score > exact.impact_score
            assert unknowns[key].impact_band in {"VERY_HIGH", "HIGH"}
        assert list(result.decision_changing_unknowns) == sorted(
            result.decision_changing_unknowns, key=lambda x: (-x.impact_score, x.key)
        )


def test_factor_counterfactuals_identify_actual_decision_reversal_conditions_without_fixed_score() -> None:
    with _session() as session:
        _, result = _ingest_and_score(session, persist=False)
        assert result.what_would_change_my_mind
        assert all(item.changes_band or item.changes_action for item in result.what_would_change_my_mind)
        assert next(x for x in result.counterfactuals if x.key == "without_reported_value").changes_band is False


def test_dimensions_do_not_double_count_signals_and_missing_need_is_not_positive() -> None:
    with _session() as session:
        _, result = _ingest_and_score(session, persist=False)
        matched = [key for dimension in result.dimensions for key in dimension.matched_signal_keys]
        assert len(matched) == len(set(matched))
        assert "site_work" not in matched and "paving" not in matched
        assert matched.count("site_activity_context") == 1
        assert matched.count("gc_awarded") == 1
        need = next(item for item in result.dimensions if item.key == "confirmed_product_need")
        assert need.internal_score == 0
        assert need.band == "NOT_CONFIRMED"
        assert need.missing_evidence


def test_comparison_cohort_excludes_missing_values_instead_of_imputing_zero() -> None:
    with _session() as session:
        project, result = _ingest_and_score(session, persist=False)
        missing = Project(
            canonical_name="Missing comparison value",
            normalized_name="missing comparison value",
            canonical_key="test:missing-comparison-value",
            source_system="test",
            external_id="missing-value",
            state=ProjectState.INGESTED,
            reported_value=None,
            currency_code="USD",
            is_synthetic=False,
        )
        lower = [
            Project(
                canonical_name=f"Lower comparison value {index}",
                normalized_name=f"lower comparison value {index}",
                canonical_key=f"test:lower-comparison-value:{index}",
                source_system="test",
                external_id=f"lower-value-{index}",
                state=ProjectState.INGESTED,
                reported_value=index + 1,
                currency_code=project.currency_code,
                is_synthetic=False,
            )
            for index in range(4)
        ]
        session.add_all([missing, *lower])
        session.flush()
        result = QualificationService(session).evaluate(project.id, persist=False)
        cohort = result.comparison_cohorts[0]
        assert cohort.total_projects == 6
        assert cohort.cohort_size == 5
        assert cohort.missing_count == 1
        assert cohort.rank == 1
        assert "never imputed as zero" in cohort.missing_data_treatment


def test_persistence_versions_configuration_and_current_assessment_state() -> None:
    with _session() as session:
        project, first = _ingest_and_score(session, persist=True)
        second = QualificationService(session).evaluate(project.id, persist=True)
        assert project.state is ProjectState.QUALIFIED
        configs = session.scalars(sa.select(ConfigVersion)).all()
        assert {(x.config_kind, x.version) for x in configs} >= {
            ("qualification", "qualification-2.0"),
            ("confidence", "confidence-1.0"),
            ("products", "products-2.1"),
        }
        assessments = session.scalars(
            sa.select(OpportunityAssessment).where(OpportunityAssessment.project_id == project.id).order_by(OpportunityAssessment.computed_at)
        ).all()
        assert len(assessments) == 2
        assert sum(1 for row in assessments if row.is_current) == 1
        current = next(row for row in assessments if row.is_current)
        assert current.commercial_fit_score == second.commercial_fit_score
        assert session.scalar(sa.select(sa.func.count()).select_from(AssessmentFactor).where(AssessmentFactor.assessment_id == current.id)) == 4
        assert session.scalar(sa.select(sa.func.count()).select_from(ProductFitAssessment).where(ProductFitAssessment.opportunity_assessment_id == current.id)) == 3


class DecimalLike:
    def __init__(self, value):
        self.value = value

    def between(self, lower, upper) -> bool:
        return lower <= self.value <= upper
