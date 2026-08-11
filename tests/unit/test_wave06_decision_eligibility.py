from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import ScoringTreatment
from app.ingestion.service import ConstructConnectIngestionService
from app.models import Base, Project, SourceEvidence, SourceObservation
from app.persistence.database import build_engine

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"


def test_observation_decision_eligibility_records_reason_and_caps_questionable_value() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConstructConnectIngestionService(session).ingest(STAFFORD)
        project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
        rows = {
            row.field_name: row
            for row in session.scalars(
                sa.select(SourceObservation).where(SourceObservation.project_id == project.id)
            ).all()
            if row.field_name in {"project.scope", "project.reported_value", "project.start_date"}
        }
        assert rows["project.scope"].decision_eligible is True
        assert rows["project.reported_value"].decision_eligible is True
        assert rows["project.reported_value"].scoring_treatment is ScoringTreatment.CAPPED
        assert "cap" in rows["project.reported_value"].decision_eligibility_reason.lower()
        assert rows["project.start_date"].decision_eligible is False
        assert rows["project.start_date"].scoring_treatment is ScoringTreatment.REVIEW

        evidence = session.scalars(
            sa.select(SourceEvidence).where(
                SourceEvidence.observation_id.in_([rows["project.reported_value"].id, rows["project.start_date"].id])
            )
        ).all()
        by_obs = {row.observation_id: row for row in evidence}
        assert by_obs[rows["project.reported_value"].id].is_permitted_for_decision is True
        assert by_obs[rows["project.start_date"].id].is_permitted_for_decision is False
