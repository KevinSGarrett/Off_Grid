from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Organization, Project
from app.persistence.database import build_engine, build_session_factory

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data/demo_seed/offgrid_demo_seed.db"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _load_wave17_verifier():
    path = ROOT / "scripts/verify_wave17_integration.py"
    if not path.exists():
        pytest.skip("internal release verifier is intentionally absent from the public repository")
    spec = importlib.util.spec_from_file_location("wave17_verifier", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_client() -> tuple[TestClient, str, str]:
    engine = build_engine(f"sqlite+pysqlite:///{SEED}")
    factory = build_session_factory(engine)
    with factory() as session:
        project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
        organization = session.scalar(
            sa.select(Organization).where(
                Organization.canonical_key == "constructconnect:company:1000647848"
            )
        )
        assert project is not None and organization is not None
        return TestClient(create_app(session_factory=factory, demo_mode=True)), str(project.id), str(organization.id)


def test_wave17_deployment_seed_contains_integrated_golden_truth() -> None:
    client, project_id, _ = _seed_client()
    assessment = client.get(f"/api/v1/projects/{project_id}/assessment").json()["assessment"]
    contacts = client.get(f"/api/v1/projects/{project_id}/contact-candidates").json()["items"]
    readiness = client.get(f"/api/v1/projects/{project_id}/crm-readiness").json()
    monday = client.get("/api/v1/monday-brief").json()
    assert assessment["disposition"] == "PURSUE"
    assert float(assessment["commercial_fit_score"]) == 80.0
    assert float(assessment["data_confidence_score"]) == 69.25
    assert contacts[0]["display_name"] == "Doug Meadows"
    assert contacts[0]["verification"]["project_association"] == "VERIFIED"
    assert contacts[0]["verification"]["rental_authority"] == "UNKNOWN"
    assert readiness["lead_ready"] is True
    assert readiness["deal_ready"] is False
    assert monday["primary_kpi"]["display"] == "N/A"


def test_wave17_seed_contains_no_direct_email_phone_or_private_host_path() -> None:
    con = sqlite3.connect(SEED)
    try:
        dump = "\n".join(con.iterdump())
    finally:
        con.close()
    assert not re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", dump, re.I)
    assert not re.search(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", dump)
    assert "/mnt/data" not in dump
    assert "context/private_source_documents" not in dump


def test_wave17_reset_is_byte_for_byte_deterministic(tmp_path: Path) -> None:
    target = tmp_path / "offgrid.db"
    cmd = [
        sys.executable,
        str(ROOT / "scripts/reset_demo_db.py"),
        "--seed",
        str(SEED),
        "--target",
        str(target),
    ]
    subprocess.check_call(cmd)
    assert _sha(target) == _sha(SEED)
    target.write_text("corrupted")
    subprocess.check_call(cmd)
    assert _sha(target) == _sha(SEED)


def test_wave17_seed_verifier_releases_temporary_sqlite_file(tmp_path: Path) -> None:
    verifier = _load_wave17_verifier()
    temporary_seed = tmp_path / "offgrid-seed.db"
    shutil.copyfile(SEED, temporary_seed)
    verifier.SEED = temporary_seed

    assert verifier.seed_checks()["status"] == "PASS"
    temporary_seed.unlink()
    assert not temporary_seed.exists()


def test_wave17_tool_versions_resolve_platform_command_shims() -> None:
    verifier = _load_wave17_verifier()

    assert verifier.command_version(["node", "--version"])
    assert verifier.command_version(["npm", "--version"])


def test_wave17_dockerfile_uses_locked_python_and_fail_closed_frontend_install() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY requirements.lock" in text
    assert "pip install --no-cache-dir -r requirements.lock" in text
    assert "package-lock.json is required" in text
    assert "npm ci --no-audit --no-fund" in text
    assert "npm install --no-audit" not in text
    assert "data/demo_seed/offgrid_demo_seed.db" in text
    assert "SERVE_WEB=true" in text


def test_wave17_openai_is_optional_runtime_extra() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    main_dependencies = text.split("[project.optional-dependencies]", 1)[0]
    assert '"openai>=2,<3"' not in main_dependencies
    assert 'ai = [' in text and '"openai>=2,<3"' in text


def test_wave17_entrypoint_restores_seed_and_fails_closed_when_missing() -> None:
    text = (ROOT / "docker/entrypoint.sh").read_text(encoding="utf-8")
    assert "DEMO_RESET_ON_START" in text
    assert "DEMO_SEED_DB" in text
    assert "FATAL: demo mode requires deployment seed" in text
    assert 'cp "$DEMO_SEED_DB" "$tmp"' in text


def test_wave17_aws_runtime_resets_to_seed_and_keeps_safe_modes() -> None:
    text = (ROOT / "infra/aws/service.yaml").read_text(encoding="utf-8")
    for pair in (
        ("DEMO_RESET_ON_START", "'true'"),
        ("OPENAI_ENABLED", "'false'"),
        ("APOLLO_MODE", "'off'"),
        ("PIPEDRIVE_MODE", "'dry_run'"),
    ):
        assert f"Name: {pair[0]}" in text
        assert f"Value: {pair[1]}" in text


def test_wave17_release_proof_records_real_blockers_instead_of_fabricating_success() -> None:
    proof_path = ROOT / "release/WAVE_17_RELEASE_PROOF.json"
    if not proof_path.exists():
        pytest.skip("internal release proof is intentionally absent from the public repository")
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert proof["seed"]["status"] == "PASS"
    assert proof["seed_privacy"]["status"] == "PASS"
    assert proof["deterministic_reset"]["status"] == "PASS"
    assert proof["live_http_access_control"]["status"] == "PASS"
    assert proof["release_exit_gate"] in {"PASS", "BLOCKED"}
    if shutil.which("docker") is None:
        assert "docker_cli" in proof["blockers"]
