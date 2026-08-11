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
        assert first.confidence_model_version == EXPECTED["confidence_model_version"]
        # Distinct measures, not one shared opaque value.
        assert first.commercial_fit_score != first.data_confidence_score


def test_reported_value_is_capped_and_counterfactual_preserves_current_disposition() -> None:
    with _session() as session:
        _, result = _ingest_and_score(session, persist=False)
        counterfactual = next(x for x in result.counterfactuals if x.key == "ignore_reported_value")
        assert abs(counterfactual.score_delta) <= EXPECTED["reported_value_max_points"]
        assert counterfactual.disposition == result.disposition
        scale = next(x for x in result.factors if x.key == "scale_duration")
        assert "large_project_value" in scale.matched_rule_keys
        # The rule is never allowed to dominate a 100-point score.
        assert EXPECTED["reported_value_max_points"] <= scale.max_points


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
        assert fits["KVT"].score_cap_applied is not None
        assert fits["KV6"].score_cap_applied is not None
        assert fits["KVP"].score_cap_applied is not None


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
        assert all(item.changes_disposition for item in result.what_would_change_my_mind)
        assert all(item.score < result.commercial_fit_score for item in result.what_would_change_my_mind)
        assert next(x for x in result.counterfactuals if x.key == "ignore_reported_value").changes_disposition is False


def test_persistence_versions_configuration_and_current_assessment_state() -> None:
    with _session() as session:
        project, first = _ingest_and_score(session, persist=True)
        second = QualificationService(session).evaluate(project.id, persist=True)
        assert project.state is ProjectState.QUALIFIED
        configs = session.scalars(sa.select(ConfigVersion)).all()
        assert {(x.config_kind, x.version) for x in configs} >= {
            ("qualification", "qualification-1.0"),
            ("confidence", "confidence-1.0"),
            ("products", "products-1.0"),
        }
        assessments = session.scalars(
            sa.select(OpportunityAssessment).where(OpportunityAssessment.project_id == project.id).order_by(OpportunityAssessment.computed_at)
        ).all()
        assert len(assessments) == 2
        assert sum(1 for row in assessments if row.is_current) == 1
        current = next(row for row in assessments if row.is_current)
        assert current.commercial_fit_score == second.commercial_fit_score
        assert session.scalar(sa.select(sa.func.count()).select_from(AssessmentFactor).where(AssessmentFactor.assessment_id == current.id)) == 7
        assert session.scalar(sa.select(sa.func.count()).select_from(ProductFitAssessment).where(ProductFitAssessment.opportunity_assessment_id == current.id)) == 3


class DecimalLike:
    def __init__(self, value):
        self.value = value

    def between(self, lower, upper) -> bool:
        return lower <= self.value <= upper
