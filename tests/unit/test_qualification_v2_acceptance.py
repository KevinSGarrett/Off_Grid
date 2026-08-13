from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
import yaml

from app.models import Project
from app.scoring.config import ScoringConfigurationError, load_qualification_config
from app.scoring.qualification import QualificationService


@pytest.fixture
def golden_state(wave14_full_state):
    session = wave14_full_state["factory"]()
    try:
        yield {"session": session}
    finally:
        session.rollback()
        session.close()


def test_v2_config_has_no_duplicate_positive_signal_contribution() -> None:
    config = load_qualification_config().data
    signals = [rule["signal"] for dimension in config["dimensions"] for rule in dimension["rules"]]
    assert len(signals) == len(set(signals))
    assert "reported_value" not in signals
    assert "large_project_value" not in signals


def test_v2_loader_rejects_accidental_duplicate_signal(tmp_path: Path) -> None:
    config = deepcopy(load_qualification_config().data)
    config["dimensions"][1]["rules"][0]["signal"] = config["dimensions"][0]["rules"][0]["signal"]
    path = tmp_path / "duplicated.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScoringConfigurationError, match="duplicated influence"):
        load_qualification_config(path)


def test_stafford_v2_is_deterministic_and_need_is_not_confirmed(golden_state) -> None:
    session = golden_state["session"]
    project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    assert project is not None
    first = QualificationService(session).evaluate(project.id, persist=False)
    second = QualificationService(session).evaluate(project.id, persist=False)
    assert first == second
    assert first.model_version == "qualification-2.0"
    assert first.overall_band == "Promising candidate"
    assert first.operational_action == "VERIFY"
    need = next(item for item in first.dimensions if item.key == "confirmed_product_need")
    assert need.internal_score == 0
    assert need.band == "NOT_CONFIRMED"
    assert all(item.applicability_status == "UNVERIFIED_APPLICABILITY" for item in first.product_fits)
    assert {item.fit_score for item in first.product_fits} == {Decimal("30.00")}
    forbidden_legacy_scores = {Decimal("59"), Decimal("70"), Decimal("75"), Decimal("80")}
    assert all(item.fit_score not in forbidden_legacy_scores for item in first.product_fits)


def test_uncertain_reported_value_cannot_change_disposition(golden_state) -> None:
    session = golden_state["session"]
    project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    result = QualificationService(session).evaluate(project.id, persist=False)
    without_value = next(item for item in result.counterfactuals if item.key == "without_reported_value")
    assert without_value.score_delta == 0
    assert without_value.band == result.overall_band
    assert without_value.action == result.operational_action


def test_comparison_cohort_excludes_missing_values_instead_of_zero(golden_state) -> None:
    session = golden_state["session"]
    project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    session.add(
        Project(
            source_system="test",
            external_id="missing-comparison",
            canonical_name="Missing comparison",
            normalized_name="missing comparison",
            canonical_key="test:missing-comparison",
            is_synthetic=False,
        )
    )
    session.flush()
    result = QualificationService(session).evaluate(project.id, persist=False)
    cohort = next(item for item in result.comparison_cohorts if item.field == "reported_value")
    assert cohort.missing_count >= 1
    assert cohort.cohort_size < cohort.total_projects
    assert "never imputed as zero" in cohort.missing_data_treatment


def test_counterfactuals_and_next_information_are_reproducible(golden_state) -> None:
    session = golden_state["session"]
    project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    first = QualificationService(session).evaluate(project.id, persist=False)
    second = QualificationService(session).evaluate(project.id, persist=False)
    assert first.counterfactuals == second.counterfactuals
    assert first.decision_changing_unknowns == second.decision_changing_unknowns
    assert first.decision_changing_unknowns[0].method_version == "value-of-next-information-1.0"
