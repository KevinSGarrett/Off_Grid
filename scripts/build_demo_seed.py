#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.demo.bootstrap import build_real_demo_database  # noqa: E402

DEFAULT_STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
DEFAULT_EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"
DEFAULT_OUTPUT = ROOT / "data/demo_seed/offgrid_demo_seed.db"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sanitize_seed(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        # Preserve role/name/domain intelligence while removing direct contact channels from the
        # image-resident seed database. The raw PDFs never enter the Docker context.
        con.execute(
            """
            UPDATE person_contact_points
            SET value = CASE contact_type
                WHEN 'EMAIL' THEN '[masked-email]'
                WHEN 'PHONE' THEN '[masked-phone]'
                ELSE '[masked-contact]'
            END,
            normalized_value = CASE contact_type
                WHEN 'EMAIL' THEN '[masked-email]'
                WHEN 'PHONE' THEN '[masked-phone]'
                ELSE '[masked-contact]'
            END,
            demo_masking_policy = 'FULL'
            """
        )
        rows = con.execute(
            "SELECT id, normalized_text FROM source_observations WHERE field_name='person.source_contact_row'"
        ).fetchall()
        for obs_id, normalized_name in rows:
            safe = f"{normalized_name or 'Source contact'} | phone/email/address masked in employer demo"
            con.execute(
                "UPDATE source_observations SET raw_value=?, normalized_text=? WHERE id=?",
                (safe, normalized_name, obs_id),
            )
            con.execute("UPDATE source_evidence SET excerpt=? WHERE observation_id=?", (safe, obs_id))

        # Remove any residual direct emails/phone numbers from free-text observation/evidence fields.
        for table, key, columns in (
            ("source_observations", "id", ("raw_value", "normalized_text", "confidence_reason", "decision_eligibility_reason")),
            ("source_evidence", "id", ("excerpt",)),
            ("quality_flags", "id", ("title", "detail")),
            ("field_history", "id", ("previous_value", "new_value")),
            ("audit_events", "id", ("detail_json",)),
        ):
            table_cols = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
            selected = [c for c in columns if c in table_cols]
            if not selected:
                continue
            for row in con.execute(f"SELECT {key}, {', '.join(selected)} FROM {table}").fetchall():
                row_id, *vals = row
                updates: dict[str, str] = {}
                for col, value in zip(selected, vals):
                    if not isinstance(value, str):
                        continue
                    masked = EMAIL_RE.sub("[masked-email]", value)
                    masked = PHONE_RE.sub("[masked-phone]", masked)
                    if masked != value:
                        updates[col] = masked
                if updates:
                    clause = ", ".join(f"{c}=?" for c in updates)
                    con.execute(
                        f"UPDATE {table} SET {clause} WHERE {key}=?",
                        (*updates.values(), row_id),
                    )

        # The source hash proves lineage but the deployment snapshot must not pretend the binary is
        # retrievable. Keep the source metadata and evidence, remove private blob references.
        con.execute("UPDATE source_documents SET blob_ref='private-source-not-packaged', is_private=1")
        # Config source paths are provenance metadata, but deployment images must not carry host paths.
        con.execute("UPDATE config_versions SET source_path = replace(source_path, ?, '') WHERE source_path LIKE ?", (str(ROOT) + '/', str(ROOT) + '/%'))
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


def assert_seed_safe(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        dump = "\n".join(con.iterdump())
    finally:
        con.close()
    failures = []
    if EMAIL_RE.search(dump):
        failures.append("direct email address remains in deployment seed")
    if PHONE_RE.search(dump):
        failures.append("direct phone number remains in deployment seed")
    if "/mnt/data" in dump or "context/private_source_documents" in dump:
        failures.append("private local source path remains in deployment seed")
    if failures:
        raise RuntimeError("; ".join(failures))


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the access-controlled employer demo seed from the real golden PDFs.")
    ap.add_argument("--stafford", type=Path, default=DEFAULT_STAFFORD)
    ap.add_argument("--ee-reed", type=Path, default=DEFAULT_EE_REED)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="offgrid-real-demo-") as td:
        raw_db = Path(td) / "real.db"
        result = build_real_demo_database(
            database_path=raw_db,
            stafford_pdf=args.stafford,
            ee_reed_pdf=args.ee_reed,
            reset=True,
        )
        shutil.copy2(raw_db, args.output)
        sanitize_seed(args.output)
        assert_seed_safe(args.output)

    print(f"seed={args.output}")
    print(f"sha256={sha256(args.output)}")
    print(f"stafford={result.project_external_id}")
    print(f"commercial_fit={result.assessment.commercial_fit_score}")
    print(f"data_confidence={result.assessment.data_confidence_score}")
    print(f"disposition={result.assessment.disposition}")
    print(f"lead_ready={result.integrations.readiness.lead_ready}")
    print(f"deal_ready={result.integrations.readiness.deal_ready}")
    print(f"external_writes={result.integrations.external_writes_executed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
