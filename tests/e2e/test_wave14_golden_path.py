from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa

from app.models import PipelineRun

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"


def test_employer_golden_path_is_coherent_end_to_end(wave14_full_state) -> None:
    client = wave14_full_state["client"]
    project_id = wave14_full_state["ids"]["project"]
    project = client.get(f"/api/v1/projects/{project_id}").json()
    assessment = client.get(f"/api/v1/projects/{project_id}/assessment").json()
    evidence = client.get(f"/api/v1/projects/{project_id}/evidence").json()
    quality = client.get(f"/api/v1/projects/{project_id}/quality").json()
    contacts = client.get(f"/api/v1/projects/{project_id}/contact-candidates").json()
    readiness = client.get(f"/api/v1/projects/{project_id}/crm-readiness").json()
    preview = client.get(f"/api/v1/projects/{project_id}/crm-preview").json()
    monday = client.get("/api/v1/monday-brief").json()

    assert project["external_id"] == "1007341663"
    assert assessment["assessment"]["disposition"] == "VERIFY"
    assert assessment["assessment"]["overall_band"] == "Promising candidate"
    assert evidence["count"] > 0
    assert {row["rule_code"] for row in quality["items"]} >= {"PROJECT_VALUE_UNCERTAINTY", "FUTURE_ACTUAL_DATE"}
    assert contacts["items"][0]["verification"]["rental_authority"] == "UNKNOWN"
    assert readiness["lead_ready"] is True and readiness["deal_ready"] is False
    assert preview["external_writes_executed"] == 0
    assert monday["primary_kpi"]["display"] == "N/A"
    rendered = json.dumps([project, assessment, evidence, quality, contacts, readiness, preview, monday])
    assert "/mnt/data" not in rendered


def test_real_duplicate_upload_returns_pipeline_run_id_and_creates_no_second_project(wave14_full_state) -> None:
    client = wave14_full_state["internal_client"]
    payload = STAFFORD.read_bytes()
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("Stafford-duplicate.pdf", payload, "application/pdf")},
        headers={"X-Request-ID": "wave14-duplicate-e2e"},
    )
    assert response.status_code == 201
    body = response.json()["result"]
    assert body["pipeline_run_id"]
    ingest = body["stages"][0]["payload"]
    assert ingest["duplicate_prevented"] is True
    assert ingest["pipeline_run_id"] == body["pipeline_run_id"]
    with wave14_full_state["factory"]() as session:
        assert session.scalar(
            sa.select(sa.func.count()).select_from(PipelineRun).where(PipelineRun.id == __import__("uuid").UUID(body["pipeline_run_id"]))
        ) == 1
