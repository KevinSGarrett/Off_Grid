from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Base
from app.persistence.database import build_engine
from app.pipeline.synthetic import generate_synthetic_projects, run_synthetic_load, seed_synthetic_portfolio


def test_synthetic_generator_is_deterministic_and_unmistakably_labeled() -> None:
    first = generate_synthetic_projects(count=25, seed=1401)
    second = generate_synthetic_projects(count=25, seed=1401)
    assert first == second
    assert all(row.is_synthetic and row.label == "SYNTHETIC" for row in first)
    assert all(row.external_id.startswith("SYNTHETIC-") and row.name.startswith("SYNTHETIC ") for row in first)


def test_300_project_scale_path_scores_every_synthetic_project_and_executes_zero_writes() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = run_synthetic_load(session, count=300, seed=1401)
        assert result.requested == result.created == result.evaluated == 300
        assert result.all_records_synthetic is True
        assert result.external_writes_executed == 0
        assert result.pursue + result.review + result.passed == 300
        assert result.projects_per_second > 0
        second = seed_synthetic_portfolio(session, generate_synthetic_projects(count=300, seed=1401))
        assert second.created == 0
        assert second.duplicates_prevented == 300
