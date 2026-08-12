from __future__ import annotations
from pathlib import Path
import sqlalchemy as sa
import pytest
from fastapi.testclient import TestClient
from app.commercial_workflow.service import Wave09CommercialWorkflowService
from app.contact_resolution.service import Wave08ContactResolutionService
from app.crm.service import Wave10IntegrationService
from app.ingestion.service import ConstructConnectIngestionService
from app.main import create_app
from app.models import Base, Project
from app.persistence.database import build_engine, build_session_factory
from app.resolution.service import Wave07ResolutionService
from app.scoring.qualification import QualificationService
ROOT=Path(__file__).resolve().parents[2]
STAFFORD=ROOT/"context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED=ROOT/"context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"
@pytest.fixture(scope="module")
def wave13_state(tmp_path_factory):
    root=tmp_path_factory.mktemp("wave13")
    engine=build_engine(f"sqlite+pysqlite:///{root/'ui.db'}");Base.metadata.create_all(engine);factory=build_session_factory(engine)
    with factory() as session:
        ingest=ConstructConnectIngestionService(session);ingest.ingest(STAFFORD);ingest.ingest(EE_REED)
        project=session.scalar(sa.select(Project).where(Project.external_id=="1007341663"));assert project is not None
        QualificationService(session).evaluate(project.id,persist=True);Wave07ResolutionService(session).run();Wave08ContactResolutionService(session).run();Wave09CommercialWorkflowService(session).run();Wave10IntegrationService(session).run();pid=project.id
    return TestClient(create_app(session_factory=factory,demo_mode=True,upload_dir=root/"uploads")),pid

def test_project_organization_discovery_supports_frontend_without_uuid_hardcoding(wave13_state):
    client,pid=wave13_state;body=client.get(f"/api/v1/projects/{pid}/organizations").json();gc=[x for x in body["items"] if x["role"]=="General Contractor"]
    assert len(gc)==1 and gc[0]["canonical_name"]=="EE Reed Construction" and gc[0]["verification_state"]=="SUPPORTED"
    assert body["project_group"]["canonical_name"]=="Stafford Technology Campus"
    assert [x["phase_label"] for x in body["project_group"]["projects"]]==["Phases 1 & 2","Phases 3 & 4"]

def test_demo_api_preserves_stafford_truth_and_unknown_authority(wave13_state):
    client,pid=wave13_state;a=client.get(f"/api/v1/projects/{pid}/assessment").json();c=client.get(f"/api/v1/projects/{pid}/contact-candidates").json();r=client.get(f"/api/v1/projects/{pid}/crm-readiness").json()
    assert a["assessment"]["disposition"]=="VERIFY" and float(a["assessment"]["commercial_fit_score"])==57.0
    assert a["assessment"]["overall_band"] == "Promising candidate"
    assert c["items"][0]["display_name"]=="Doug Meadows" and c["items"][0]["verification"]["project_association"]=="VERIFIED" and c["items"][0]["verification"]["rental_authority"]=="UNKNOWN"
    assert r["lead_ready"] is True and r["deal_ready"] is False

def test_demo_api_evidence_has_no_private_server_paths(wave13_state):
    client,pid=wave13_state;e=client.get(f"/api/v1/projects/{pid}/evidence").json();assert e["demo_mode"] is True and e["count"]>0
    assert all("/mnt/data" not in (x["excerpt"] or "") for x in e["items"])

def test_monday_kpi_does_not_fabricate_outcomes(wave13_state):
    client,_=wave13_state;b=client.get("/api/v1/monday-brief").json();assert b["primary_kpi"]["display"]=="N/A" and b["primary_kpi"]["status"]=="PRODUCTION_OUTCOME_HISTORY_NOT_CONNECTED"

def test_openapi_inventory_includes_wave13_read_only_discovery_projection(wave13_state):
    client, _ = wave13_state
    schema = client.get('/openapi.json').json()
    paths = schema['paths']
    methods = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}
    operations = sum(1 for path in paths.values() for method in path if method.lower() in methods)
    assert '/api/v1/projects/{project_id}/organizations' in paths
    assert len(paths) == 32
    assert '/api/v1/analyst/query/stream' in paths
    assert operations == 33


def test_decision_card_action_uses_a_separate_grid_row() -> None:
    css = (ROOT / "apps/web/src/styles.css").read_text(encoding="utf-8")
    assert ".decision-card .score-top > .pill" in css
    assert "grid-column: 2" in css
    assert "justify-self: start" in css


def test_compact_action_status_stacks_at_the_mobile_layout_breakpoint() -> None:
    css = (ROOT / "apps/web/src/styles.css").read_text(encoding="utf-8")
    mobile = css.split("@media (max-width: 600px)", 1)[1].split("@media (max-width: 410px)", 1)[0]
    assert ".ranked-action.compact { grid-template-columns: 25px minmax(0, 1fr); }" in mobile
    assert ".ranked-action.compact > .pill { grid-column: 2; justify-self: start; margin-top: 3px; }" in mobile
    assert ".ranked-action > span:first-child" in css
    assert ".ranked-action.compact > span:first-child" in css
    assert ".ranked-action.compact > span {" not in css
