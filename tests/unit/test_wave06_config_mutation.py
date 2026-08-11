from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
import yaml
from sqlalchemy.orm import Session

from app.ingestion.service import ConstructConnectIngestionService
from app.models import Base, Project
from app.persistence.database import build_engine
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"


def test_mutating_versioned_rule_changes_score_without_code_or_project_special_case(tmp_path: Path) -> None:
    original = yaml.safe_load((ROOT / "config/qualification.yaml").read_text(encoding="utf-8"))
    mutated = yaml.safe_load((ROOT / "config/qualification.yaml").read_text(encoding="utf-8"))
    mutated["model"]["version"] = "qualification-test-mutated"
    mutated["factors"][0]["rules"][0]["points"] -= 1
    path = tmp_path / "qualification.yaml"
    path.write_text(yaml.safe_dump(mutated, sort_keys=False), encoding="utf-8")

    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConstructConnectIngestionService(session).ingest(STAFFORD)
        project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
        baseline = QualificationService(session).evaluate(project.id, persist=False)
        changed = QualificationService(session, qualification_config=path).evaluate(project.id, persist=False)
        assert baseline.commercial_fit_score != changed.commercial_fit_score
        assert baseline.commercial_fit_score - changed.commercial_fit_score == 1
        assert original["model"]["version"] != mutated["model"]["version"]
