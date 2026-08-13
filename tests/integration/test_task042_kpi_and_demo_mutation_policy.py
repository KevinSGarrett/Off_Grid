from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from app.api.route_policy import MUTATION_CAPABLE_ROUTES, ROUTE_EFFECTS, RouteEffect
from app.domain.states import CommercialOutcomeType
from app.main import create_app
from app.models import (
    CommercialMotion,
    CommercialOutcome,
    ContactCandidate,
    Project,
    WorkflowException,
)
from app.reporting.metrics import build_employer_metrics
from fastapi.testclient import TestClient


def _database_fingerprint(factory) -> str:
    with factory() as session:
        inspector = sa.inspect(session.get_bind())
        snapshot: dict[str, list[str]] = {}
        for table in sorted(inspector.get_table_names()):
            columns = [column["name"] for column in inspector.get_columns(table)]
            quoted = ", ".join(f'"{column}"' for column in columns)
            rows = session.execute(sa.text(f'SELECT {quoted} FROM "{table}"')).mappings()
            snapshot[table] = sorted(
                json.dumps({key: str(value) for key, value in row.items()}, sort_keys=True)
                for row in rows
            )
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def _filesystem_fingerprint(root: Path) -> str:
    rows = []
    if root.exists():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            rows.append(
                (path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
            )
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def test_every_http_route_has_an_explicit_effect_classification(wave14_full_state) -> None:
    openapi = wave14_full_state["client"].get("/openapi.json").json()
    actual = {
        (method.upper(), path)
        for path, operations in openapi["paths"].items()
        for method in operations
    }
    assert actual == set(ROUTE_EFFECTS)
    assert {effect for effect in ROUTE_EFFECTS.values()} == set(RouteEffect)
    assert len(MUTATION_CAPABLE_ROUTES) == 6


def test_system_sourced_kpi_enforces_provenance_time_and_synthetic_boundaries(
    wave14_full_state,
) -> None:
    now = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    with wave14_full_state["factory"]() as session:
        project = session.get(Project, wave14_full_state["ids"]["project"])
        motion = session.scalar(
            sa.select(CommercialMotion).where(CommercialMotion.project_id == project.id)
        )
        assert project is not None and motion is not None

        baseline = build_employer_metrics(session, now=now)["primary_kpi"]
        assert baseline["display"] == "N/A" and baseline["value"] is None

        session.add(
            CommercialOutcome(
                project_id=project.id,
                commercial_motion_id=motion.id,
                outcome_type=CommercialOutcomeType.RESPONDED,
                source="offgrid_pipeline:event-history-connected",
                observed_at=now,
            )
        )
        session.flush()
        connected_zero = build_employer_metrics(session, now=now)["primary_kpi"]
        assert connected_zero["display"] == "0" and connected_zero["status"] == "AVAILABLE"

        for source, observed_at in (
            ("manual-entry", now),
            ("fixture:demo", now),
            ("offgridXpipeline:event-near-match", now),
            ("offgrid_pipeline:", now),
            ("offgrid_pipeline:event-old", now - timedelta(days=31)),
            ("offgrid_pipeline:event-future", now + timedelta(seconds=1)),
        ):
            session.add(
                CommercialOutcome(
                    project_id=project.id,
                    commercial_motion_id=motion.id,
                    outcome_type=CommercialOutcomeType.DEMO_BOOKED,
                    source=source,
                    observed_at=observed_at,
                )
            )
        session.flush()
        assert build_employer_metrics(session, now=now)["primary_kpi"]["value"] == 0

        session.add(
            CommercialOutcome(
                project_id=project.id,
                commercial_motion_id=motion.id,
                outcome_type=CommercialOutcomeType.DEMO_BOOKED,
                source="pipedrive:activity-123",
                observed_at=now,
            )
        )
        session.flush()
        assert build_employer_metrics(session, now=now)["primary_kpi"]["value"] == 1

        project.is_synthetic = True
        session.flush()
        synthetic = build_employer_metrics(session, now=now)["primary_kpi"]
        assert synthetic["display"] == "N/A" and synthetic["value"] is None
        session.rollback()


def test_every_mutation_capable_route_is_fail_closed_without_state_change(
    wave14_full_state, monkeypatch
) -> None:
    from app.api.routes import crm as crm_route

    def forbidden_crm_call(*_args, **_kwargs):
        raise AssertionError("CRM preview/external boundary ran in demo mode")

    monkeypatch.setattr(crm_route, "_run", forbidden_crm_call)
    upload_root = wave14_full_state["root"] / "task042-demo-uploads"
    client = TestClient(
        create_app(
            session_factory=wave14_full_state["factory"],
            demo_mode=True,
            upload_dir=upload_root,
        )
    )
    project_id = wave14_full_state["ids"]["project"]
    with wave14_full_state["factory"]() as session:
        candidate_id = session.scalar(sa.select(ContactCandidate.id).limit(1)) or uuid4()
        exception_id = session.scalar(sa.select(WorkflowException.id).limit(1)) or uuid4()
    before_db = _database_fingerprint(wave14_full_state["factory"])
    before_files = _filesystem_fingerprint(upload_root)

    attempts = (
        client.post(
            "/api/v1/ingest", files={"file": ("blocked.pdf", b"blocked", "application/pdf")}
        ),
        client.post(
            f"/api/v1/projects/{project_id}/outcomes",
            json={
                "outcome_type": "DEMO_BOOKED",
                "source": "offgrid_pipeline:blocked",
                "commercial_motion_id": str(uuid4()),
            },
        ),
        client.post(
            f"/api/v1/contacts/{candidate_id}/verification",
            json={
                "dimension": "employment",
                "verification_type": "COMPANY_SOURCE",
                "outcome": "VERIFIED",
                "verified_by": "blocked",
                "note": "blocked",
            },
        ),
        client.post(
            f"/api/v1/exceptions/{exception_id}/resolution",
            json={
                "action": "VERIFY",
                "note": "blocked",
            },
        ),
        client.post(f"/api/v1/projects/{project_id}/crm-sync"),
        client.post(f"/api/v1/projects/{project_id}/pipeline/refresh"),
    )
    assert len(attempts) == len(MUTATION_CAPABLE_ROUTES)
    assert all(response.status_code == 403 for response in attempts)
    assert all(response.json()["detail"]["code"] == "DEMO_MODE_READ_ONLY" for response in attempts)
    assert _database_fingerprint(wave14_full_state["factory"]) == before_db
    assert _filesystem_fingerprint(upload_root) == before_files
