#!/usr/bin/env python3
"""Prove that the public demo seed matches schema, config, and current services."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.commercial_workflow.service import CommercialWorkflowService
from app.contact_resolution.service import ContactResolutionService
from app.crm.service import CommercialIntegrationService
from app.main import create_app
from app.models import (
    AssessmentFactor,
    AuditEvent,
    Base,
    CommercialMotion,
    ContactAssessment,
    ContactCandidate,
    CRMRecord,
    CRMSyncAttempt,
    NextAction,
    OpportunityAssessment,
    ProductFitAssessment,
    Project,
    VerificationEvent,
)
from app.persistence.database import build_engine, build_session_factory
from app.scoring.qualification import QualificationService

DEFAULT_SEED = ROOT / "data" / "demo_seed" / "offgrid_demo_seed.db"
CONFIG_ROOT = ROOT / "config"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def schema_signature(path: Path, *, include_alembic: bool = False) -> dict[str, list[str]]:
    connection = sqlite3.connect(path)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if not include_alembic:
            tables.discard("alembic_version")
        return {
            table: sorted(
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            )
            for table in sorted(tables)
        }
    finally:
        connection.close()


def model_signature() -> dict[str, list[str]]:
    return {
        table.name: sorted(column.name for column in table.columns)
        for table in Base.metadata.sorted_tables
    }


def migration_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if not head:
        raise RuntimeError("Alembic has no unique migration head")
    return head


def upgrade(path: Path) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{path.as_posix()}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )


def database_health(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    try:
        return {
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_errors": connection.execute("PRAGMA foreign_key_check").fetchall(),
            "alembic_versions": [
                row[0] for row in connection.execute("SELECT version_num FROM alembic_version")
            ],
        }
    finally:
        connection.close()


def config_bindings(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT config_kind, version, content_sha256, source_path "
            "FROM config_versions WHERE is_active=1 ORDER BY config_kind"
        ).fetchall()
    finally:
        connection.close()
    errors: list[str] = []
    bindings: list[dict[str, str]] = []
    for kind, version, expected_hash, source_path in rows:
        normalized = str(source_path).replace("\\", "/")
        candidate = ROOT / normalized
        actual_hash = sha256(candidate) if candidate.is_file() else "MISSING"
        if not normalized.startswith("config/") or normalized.count("/") != 1:
            errors.append(f"{kind} source path is not repository-relative: {source_path}")
        if actual_hash != expected_hash:
            errors.append(f"{kind} hash mismatch: expected={expected_hash} actual={actual_hash}")
        bindings.append(
            {
                "kind": str(kind),
                "version": str(version),
                "source_path": normalized,
                "sha256": str(expected_hash),
            }
        )
    return {"bindings": bindings, "errors": errors}


COUNT_MODELS = (
    OpportunityAssessment,
    AssessmentFactor,
    ProductFitAssessment,
    ContactCandidate,
    ContactAssessment,
    VerificationEvent,
    CommercialMotion,
    NextAction,
    CRMRecord,
    CRMSyncAttempt,
    AuditEvent,
)


def service_coherence(path: Path) -> dict[str, Any]:
    engine = build_engine(f"sqlite+pysqlite:///{path.as_posix()}")
    factory = build_session_factory(engine)
    try:
        with factory() as session:
            project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
            if project is None:
                raise RuntimeError("Stafford project is absent from seed")

            def counts() -> dict[str, int]:
                return {
                    model.__tablename__: int(
                        session.scalar(sa.select(sa.func.count()).select_from(model)) or 0
                    )
                    for model in COUNT_MODELS
                }

            persisted = session.scalar(
                sa.select(OpportunityAssessment).where(
                    OpportunityAssessment.project_id == project.id,
                    OpportunityAssessment.is_current.is_(True),
                )
            )
            if persisted is None:
                raise RuntimeError("Current Stafford assessment is absent from seed")
            persisted_products = {
                row.product_code: row.fit_band
                for row in session.scalars(
                    sa.select(ProductFitAssessment).where(
                        ProductFitAssessment.opportunity_assessment_id == persisted.id
                    )
                )
            }
            before = counts()
            recomputed = QualificationService(session).evaluate(project.id, persist=False)
            contacts = ContactResolutionService(session).run(project_external_id="1007341663")
            workflow = CommercialWorkflowService(session).run(project_external_id="1007341663")
            crm = CommercialIntegrationService(session, demo_mode=True).run("1007341663")
            after = counts()
            recomputed_products = {
                row.product_code: row.applicability_status for row in recomputed.product_fits
            }
            errors: list[str] = []
            if Decimal(persisted.commercial_fit_score) != recomputed.commercial_fit_score:
                errors.append("persisted commercial fit differs from current recomputation")
            if Decimal(persisted.data_confidence_score) != recomputed.data_confidence_score:
                errors.append("persisted Data Confidence differs from current recomputation")
            if persisted.disposition != recomputed.operational_action:
                errors.append("persisted disposition differs from current recommended action")
            if persisted_products != recomputed_products:
                errors.append("persisted product applicability differs from current recomputation")
            if before != after:
                errors.append("current services changed canonical row counts on an idempotent rerun")
            if contacts.authority_verified_count != 0:
                errors.append("rental authority became verified without evidence")
            if crm.external_writes_executed != 0:
                errors.append("demo coherence check executed an external write")
            if crm.readiness.deal_ready:
                errors.append("Stafford Deal became ready while required evidence is unresolved")
            if workflow.first_call_kit.version != "stafford-first-call-kit-1.0":
                errors.append("seed first-call kit does not use the current canonical version")
            return {
                "errors": errors,
                "before_counts": before,
                "after_counts": after,
                "stafford": {
                    "commercial_fit": str(recomputed.commercial_fit_score),
                    "data_confidence": str(recomputed.data_confidence_score),
                    "band": recomputed.overall_band,
                    "action": recomputed.operational_action,
                    "product_applicability": recomputed_products,
                    "contact_candidates": len(contacts.candidates),
                    "rental_authority_verified": contacts.authority_verified_count,
                    "first_call_kit": workflow.first_call_kit.version,
                    "lead_ready": crm.readiness.lead_ready,
                    "deal_ready": crm.readiness.deal_ready,
                    "external_writes": crm.external_writes_executed,
                },
            }
    finally:
        engine.dispose()


def read_only_restore_proof(seed: Path, runtime: Path) -> dict[str, Any]:
    shutil.copyfile(seed, runtime)
    seed_hash = sha256(seed)
    engine = build_engine(f"sqlite+pysqlite:///{runtime.as_posix()}")
    factory = build_session_factory(engine)
    try:
        with TestClient(create_app(session_factory=factory, demo_mode=True)) as client:
            projects = client.get("/api/v1/projects?limit=500")
            projects.raise_for_status()
            stafford = next(
                row for row in projects.json()["items"] if row["external_id"] == "1007341663"
            )
            for path in (
                "/api/v1/health",
                f"/api/v1/projects/{stafford['id']}/assessment",
                f"/api/v1/projects/{stafford['id']}/contact-candidates",
                f"/api/v1/projects/{stafford['id']}/actions",
                f"/api/v1/projects/{stafford['id']}/crm-readiness",
            ):
                response = client.get(path)
                response.raise_for_status()
    finally:
        engine.dispose()
    after_read_hash = sha256(runtime)
    runtime.write_bytes(b"corrupted")
    shutil.copyfile(seed, runtime)
    restored_hash = sha256(runtime)
    return {
        "seed_sha256": seed_hash,
        "after_read_sha256": after_read_hash,
        "restored_sha256": restored_hash,
        "identical": seed_hash == after_read_hash == restored_hash,
    }


def verify(seed: Path = DEFAULT_SEED) -> dict[str, Any]:
    errors: list[str] = []
    head = migration_head()
    health = database_health(seed)
    if health["integrity"] != "ok" or health["foreign_key_errors"]:
        errors.append("seed database integrity or foreign-key check failed")
    if health["alembic_versions"] != [head]:
        errors.append(
            f"seed migration binding differs from head: {health['alembic_versions']} != {[head]}"
        )

    with tempfile.TemporaryDirectory(prefix="offgrid-seed-coherence-") as temporary:
        root = Path(temporary)
        migrated = root / "migrated.db"
        runtime = root / "runtime.db"
        prebuilt = root / "prebuilt.db"
        service_copy = root / "service.db"
        upgrade(migrated)
        shutil.copyfile(seed, prebuilt)
        upgrade(prebuilt)
        model = model_signature()
        seed_schema = schema_signature(seed)
        migrated_schema = schema_signature(migrated)
        prebuilt_schema = schema_signature(prebuilt)
        if seed_schema != model:
            errors.append("seed schema differs from current SQLAlchemy model metadata")
        if migrated_schema != model:
            errors.append("empty Alembic-upgraded schema differs from current model metadata")
        if prebuilt_schema != model:
            errors.append("prebuilt seed cannot upgrade cleanly to current migration head")
        restore = read_only_restore_proof(seed, runtime)
        if not restore["identical"]:
            errors.append("read-only use or reset did not preserve the exact seed baseline")
        shutil.copyfile(seed, service_copy)
        services = service_coherence(service_copy)

    configs = config_bindings(seed)
    errors.extend(configs["errors"])
    errors.extend(services["errors"])
    return {
        "schema_version": "offgrid-demo-seed-coherence-1.0",
        "status": "PASS" if not errors else "FAIL",
        "seed": {"path": seed.as_posix(), "sha256": sha256(seed), "bytes": seed.stat().st_size},
        "migration_head": head,
        "database_health": health,
        "schemas": {
            "seed_model_match": seed_schema == model,
            "empty_migration_model_match": migrated_schema == model,
            "prebuilt_upgrade_model_match": prebuilt_schema == model,
        },
        "config": configs,
        "services": services,
        "read_only_restore": restore,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.seed.resolve())
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
