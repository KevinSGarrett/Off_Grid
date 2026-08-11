from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.demo.bootstrap import build_real_demo_database
from app.main import create_app
from app.models import Organization, Project
from app.persistence.database import build_engine, build_session_factory

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


def test_wave17_real_private_sources_build_the_same_integrated_truth(tmp_path: Path) -> None:
    db = tmp_path / "real-integration.db"
    result = build_real_demo_database(
        database_path=db,
        stafford_pdf=STAFFORD,
        ee_reed_pdf=EE_REED,
        reset=True,
    )
    assert result.project_external_id == "1007341663"
    assert result.organization_canonical_key == "constructconnect:company:1000647848"
    assert result.assessment.disposition == "PURSUE"
    assert float(result.assessment.commercial_fit_score) == 80.0
    assert float(result.assessment.data_confidence_score) == 69.25
    assert result.integrations.readiness.lead_ready is True
    assert result.integrations.readiness.deal_ready is False
    assert result.integrations.external_writes_executed == 0

    engine = build_engine(f"sqlite+pysqlite:///{db}")
    factory = build_session_factory(engine)
    with factory() as session:
        project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
        organization = session.scalar(
            sa.select(Organization).where(
                Organization.canonical_key == "constructconnect:company:1000647848"
            )
        )
        assert project is not None and organization is not None
        project_id = project.id
    client = TestClient(create_app(session_factory=factory, demo_mode=True))
    evidence = client.get(f"/api/v1/projects/{project_id}/evidence").json()
    quality = client.get(f"/api/v1/projects/{project_id}/quality").json()
    assert evidence["count"] > 0
    codes = {item["rule_code"] for item in quality["items"]}
    assert {"PROJECT_VALUE_UNCERTAINTY", "FUTURE_ACTUAL_DATE"}.issubset(codes)
