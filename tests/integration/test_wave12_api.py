from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.commercial_workflow.service import Wave09CommercialWorkflowService
from app.contact_resolution.service import Wave08ContactResolutionService
from app.crm.service import Wave10IntegrationService
from app.ingestion.service import ConstructConnectIngestionService
from app.main import create_app
from app.models import Base, ContactCandidate, Organization, Project, WorkflowException
from app.persistence.database import build_engine, build_session_factory
from app.resolution.service import Wave07ResolutionService
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


@pytest.fixture(scope="module")
def api_state(tmp_path_factory):
    root = tmp_path_factory.mktemp("wave12-api")
    db_path = root / "api.db"
    engine = build_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    with factory() as session:
        ingest = ConstructConnectIngestionService(session)
        ingest.ingest(STAFFORD)
        ingest.ingest(EE_REED)
        project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
        assert project is not None
        QualificationService(session).evaluate(project.id, persist=True)
        Wave07ResolutionService(session).run()
        Wave08ContactResolutionService(session).run()
        Wave09CommercialWorkflowService(session).run()
        Wave10IntegrationService(session).run()
        organization = session.scalar(sa.select(Organization).where(Organization.canonical_name == "EE Reed Construction"))
        assert organization is not None
        candidate = session.scalar(
            sa.select(ContactCandidate)
            .where(ContactCandidate.project_id == project.id, ContactCandidate.is_current.is_(True))
            .order_by(ContactCandidate.rank.asc())
        )
        assert candidate is not None
        exception = session.scalar(sa.select(WorkflowException).where(WorkflowException.project_id == project.id))
        ids = {
            "project": project.id,
            "organization": organization.id,
            "candidate": candidate.id,
            "exception": exception.id if exception else None,
        }
    app = create_app(session_factory=factory, demo_mode=False, upload_dir=root / "uploads")
    return {"client": TestClient(app), "factory": factory, "ids": ids, "root": root}


def test_wave12_openapi_exposes_major_route_families(api_state) -> None:
    client = api_state["client"]
    paths = client.get("/openapi.json").json()["paths"]
    required = {
        "/api/v1/ingest",
        "/api/v1/projects",
        "/api/v1/projects/{project_id}",
        "/api/v1/projects/{project_id}/assessment",
        "/api/v1/projects/{project_id}/signals",
        "/api/v1/projects/{project_id}/quality",
        "/api/v1/projects/{project_id}/evidence",
        "/api/v1/organizations/{organization_id}",
        "/api/v1/organizations/{organization_id}/contacts",
        "/api/v1/projects/{project_id}/contact-candidates",
        "/api/v1/contacts/{contact_id}/verification",
        "/api/v1/exceptions",
        "/api/v1/projects/{project_id}/actions",
        "/api/v1/projects/{project_id}/commercial-motions",
        "/api/v1/projects/{project_id}/crm-readiness",
        "/api/v1/projects/{project_id}/crm-preview",
        "/api/v1/projects/{project_id}/crm-sync",
        "/api/v1/pipeline/runs",
        "/api/v1/metrics",
        "/api/v1/monday-brief",
        "/api/v1/analyst/query",
        "/api/v1/executive-brief/generate",
    }
    assert required <= set(paths)


def test_project_assessment_signals_quality_and_evidence(api_state) -> None:
    client = api_state["client"]
    project_id = api_state["ids"]["project"]
    project = client.get(f"/api/v1/projects/{project_id}")
    assert project.status_code == 200
    assert project.json()["external_id"] == "1007341663"

    assessment = client.get(f"/api/v1/projects/{project_id}/assessment")
    assert assessment.status_code == 200
    assert assessment.json()["assessment"]["disposition"] == "PURSUE"
    assert assessment.json()["product_fits"]

    signals = client.get(f"/api/v1/projects/{project_id}/signals")
    assert signals.status_code == 200
    assert any(row["key"] == "data_center" for row in signals.json()["items"])

    quality = client.get(f"/api/v1/projects/{project_id}/quality")
    assert quality.status_code == 200
    codes = {row["rule_code"] for row in quality.json()["items"]}
    assert "FUTURE_ACTUAL_DATE" in codes
    assert "PROJECT_VALUE_UNCERTAINTY" in codes

    evidence = client.get(f"/api/v1/projects/{project_id}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["count"] > 0
    assert all(row["evidence_id"].startswith("src:") for row in evidence.json()["items"])


def test_sensitivity_is_non_persisting_and_keeps_value_counterfactual(api_state) -> None:
    client = api_state["client"]
    project_id = api_state["ids"]["project"]
    response = client.post(f"/api/v1/projects/{project_id}/sensitivity")
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is False
    by_key = {row["key"]: row for row in body["counterfactuals"]}
    assert by_key["ignore_reported_value"]["disposition"] == "PURSUE"


def test_organization_contacts_and_contact_candidates_are_queryable(api_state) -> None:
    client = api_state["client"]
    organization_id = api_state["ids"]["organization"]
    project_id = api_state["ids"]["project"]
    org = client.get(f"/api/v1/organizations/{organization_id}")
    assert org.status_code == 200
    assert org.json()["canonical_name"] == "EE Reed Construction"
    contacts = client.get(f"/api/v1/organizations/{organization_id}/contacts")
    assert contacts.status_code == 200
    assert contacts.json()["count"] > 0
    candidates = client.get(f"/api/v1/projects/{project_id}/contact-candidates")
    assert candidates.status_code == 200
    assert candidates.json()["count"] > 0
    assert all("rental_authority" in row["verification"] for row in candidates.json()["items"] if row["verification"])


def test_commercial_motion_actions_and_crm_contracts_remain_fail_closed(api_state) -> None:
    client = api_state["client"]
    project_id = api_state["ids"]["project"]
    motions = client.get(f"/api/v1/projects/{project_id}/commercial-motions")
    actions = client.get(f"/api/v1/projects/{project_id}/actions")
    assert motions.status_code == actions.status_code == 200
    assert {row["motion_type"] for row in motions.json()["items"]} == {"CONTRACTOR", "RENTAL_HOUSE"}
    assert actions.json()["items"]

    readiness = client.get(f"/api/v1/projects/{project_id}/crm-readiness")
    assert readiness.status_code == 200
    assert readiness.json()["lead_ready"] is True
    assert readiness.json()["deal_ready"] is False

    preview = client.get(f"/api/v1/projects/{project_id}/crm-preview")
    assert preview.status_code == 200
    assert preview.json()["external_writes_executed"] == 0

    command = client.post(f"/api/v1/projects/{project_id}/crm-sync")
    assert command.status_code == 200
    assert command.json()["external_write_performed"] is False
    assert command.json()["command_status"] == "PREVIEWED"


def test_pipeline_runs_metrics_and_monday_brief(api_state) -> None:
    client = api_state["client"]
    runs = client.get("/api/v1/pipeline/runs")
    assert runs.status_code == 200
    assert runs.json()["count"] >= 2
    first_id = runs.json()["items"][0]["id"]
    detail = client.get(f"/api/v1/pipeline/runs/{first_id}")
    assert detail.status_code == 200
    assert detail.json()["events"]

    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["primary_kpi"]["display"] == "N/A"
    assert metrics.json()["diagnostics"]["projects_qualified"] >= 1

    brief = client.get("/api/v1/monday-brief")
    assert brief.status_code == 200
    assert brief.json()["top_opportunity"]["external_id"] == "1007341663"
    assert brief.json()["primary_kpi"]["display"] == "N/A"


def test_disabled_openai_analyst_and_brief_degrade_without_breaking_api(api_state) -> None:
    client = api_state["client"]
    project_id = api_state["ids"]["project"]
    analyst = client.post(
        "/api/v1/analyst/query",
        json={"project_id": str(project_id), "question": "What is blocking commercial progression?"},
    )
    assert analyst.status_code == 200
    assert analyst.json()["status"] == "DISABLED"
    assert analyst.json()["external_request_executed"] is False

    executive = client.post("/api/v1/executive-brief/generate", json={"context": {"project_id": str(project_id)}})
    assert executive.status_code == 200
    assert executive.json()["status"] == "DISABLED"
    assert executive.json()["external_request_executed"] is False


def test_contact_verification_rejects_weak_authority_evidence(api_state) -> None:
    client = api_state["client"]
    candidate_id = api_state["ids"]["candidate"]
    response = client.post(
        f"/api/v1/contacts/{candidate_id}/verification",
        json={
            "dimension": "rental_authority",
            "verification_type": "MANUAL_RESEARCH",
            "outcome": "VERIFIED",
            "verified_by": "wave12-test",
            "note": "Weak research must not verify authority.",
        },
    )
    assert response.status_code == 422
    assert "Rental authority may be VERIFIED" in response.json()["detail"]["message"]


def test_demo_mode_blocks_internal_mutation_commands(api_state) -> None:
    factory = api_state["factory"]
    demo_client = TestClient(create_app(session_factory=factory, demo_mode=True, upload_dir=api_state["root"] / "demo-uploads"))
    candidate_id = api_state["ids"]["candidate"]
    verify = demo_client.post(
        f"/api/v1/contacts/{candidate_id}/verification",
        json={
            "dimension": "employment",
            "verification_type": "COMPANY_SOURCE",
            "outcome": "VERIFIED",
            "verified_by": "demo",
            "note": "Should be blocked by demo mode.",
        },
    )
    assert verify.status_code == 403
    assert verify.json()["detail"]["code"] == "DEMO_MODE_READ_ONLY"


def test_ingest_endpoint_uses_real_parser_and_is_idempotent(tmp_path) -> None:
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'ingest.db'}")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    client = TestClient(create_app(session_factory=factory, demo_mode=False, upload_dir=tmp_path / "uploads"))
    payload = STAFFORD.read_bytes()
    first = client.post("/api/v1/ingest", files={"file": ("Stafford.pdf", payload, "application/pdf")})
    second = client.post("/api/v1/ingest", files={"file": ("Stafford.pdf", payload, "application/pdf")})
    assert first.status_code == 201
    assert second.status_code == 201
    first_ingest = first.json()["result"]["stages"][0]["payload"]
    second_ingest = second.json()["result"]["stages"][0]["payload"]
    assert first_ingest["created_document"] is True
    assert second_ingest["duplicate_prevented"] is True
    with factory() as session:
        assert session.scalar(sa.select(sa.func.count()).select_from(Project).where(Project.external_id == "1007341663")) == 1


def test_project_pipeline_refresh_reuses_owner_wave_services(api_state) -> None:
    client = api_state["client"]
    project_id = api_state["ids"]["project"]
    response = client.post(f"/api/v1/projects/{project_id}/pipeline/refresh")
    assert response.status_code == 200
    stages = {row["stage"]: row for row in response.json()["stages"]}
    assert stages["qualification"]["status"] == "SUCCEEDED"
    assert stages["crm_preview"]["status"] == "SUCCEEDED"
