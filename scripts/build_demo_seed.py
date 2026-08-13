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

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.demo.bootstrap import build_real_demo_database

DEFAULT_STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
DEFAULT_EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"
DEFAULT_OUTPUT = ROOT / "data/demo_seed/offgrid_demo_seed.db"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
WINDOWS_HOST_PATH_RE = re.compile(r"[A-Z]:\\(?:Users|Off_Grid)\\", re.IGNORECASE)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sanitize_seed(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        # Preserve the structural behavior of all private source-directory rows without
        # redistributing the licensed-source-only identities. Publicly researched people
        # are separate records and are intentionally unaffected by this transformation.
        private_people = con.execute(
            """
            SELECT DISTINCT p.id, p.display_name
            FROM persons p
            JOIN source_observations so ON so.person_id = p.id
            WHERE so.field_name = 'person.source_contact_row'
            ORDER BY p.id
            """
        ).fetchall()
        anonymization_map: dict[str, str] = {}
        for index, (person_id, original_name) in enumerate(private_people, start=1):
            label = f"Source Contact {index:02d}"
            normalized = label.casefold()
            anonymization_map[str(original_name)] = label
            con.execute(
                """
                UPDATE persons
                SET display_name=?, normalized_name=?, given_name=NULL, family_name=NULL
                WHERE id=?
                """,
                (label, normalized, person_id),
            )
            aliases = con.execute(
                "SELECT id FROM person_aliases WHERE person_id=? ORDER BY id",
                (person_id,),
            ).fetchall()
            for alias_index, (alias_id,) in enumerate(aliases, start=1):
                alias = label if alias_index == 1 else f"{label} Alias {alias_index:02d}"
                con.execute(
                    "UPDATE person_aliases SET alias=?, normalized_alias=? WHERE id=?",
                    (alias, alias.casefold(), alias_id),
                )
            observations = con.execute(
                """
                SELECT id
                FROM source_observations
                WHERE person_id=? AND field_name='person.source_contact_row'
                ORDER BY id
                """,
                (person_id,),
            ).fetchall()
            for observation_index, (observation_id,) in enumerate(observations, start=1):
                safe = f"{label} | private source contact details omitted from public demo"
                observation_fingerprint = hashlib.sha256(
                    f"public-demo:{label}:{observation_index}".encode()
                ).hexdigest()
                evidence_fingerprint = hashlib.sha256(
                    f"public-demo-evidence:{label}:{observation_index}".encode()
                ).hexdigest()
                con.execute(
                    """
                    UPDATE source_observations
                    SET raw_value=?, normalized_text=?, observation_fingerprint=?
                    WHERE id=?
                    """,
                    (safe, label, observation_fingerprint, observation_id),
                )
                con.execute(
                    """
                    UPDATE source_evidence
                    SET excerpt=?, evidence_fingerprint=?
                    WHERE observation_id=?
                    """,
                    (safe, evidence_fingerprint, observation_id),
                )

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

        # Private filenames and content hashes are unnecessary redistribution metadata. Retain
        # two deterministic source sentinels so provenance relationships remain demonstrable.
        documents = con.execute(
            """
            SELECT id, content_sha256
            FROM source_documents
            ORDER BY source_type, report_type, external_id, id
            """
        ).fetchall()
        for index, (document_id, original_content_hash) in enumerate(documents, start=1):
            label = f"private-source-{index:02d}"
            public_hash = hashlib.sha256(
                f"offgrid-public-demo:{label}:not-distributed".encode()
            ).hexdigest()
            anonymization_map[str(original_content_hash)] = public_hash
            con.execute(
                """
                UPDATE source_documents
                SET external_id=?, original_filename=?, content_sha256=?,
                    blob_ref='private-source-not-packaged', is_private=1
                WHERE id=?
                """,
                (label, f"{label}.pdf", public_hash, document_id),
            )

        # Retain the decision-useful fact while omitting the licensed report's prose.
        safe_description = (
            "Source report described a multi-phase technology campus and states phases 1 & 2 are underway; "
            "detailed licensed prose is omitted from the public demo."
        )
        description_rows = con.execute(
            "SELECT id FROM source_observations WHERE field_name='project.description'"
        ).fetchall()
        for (observation_id,) in description_rows:
            con.execute(
                """
                UPDATE source_observations
                SET raw_value=?, normalized_text=?, observation_fingerprint=?
                WHERE id=?
                """,
                (
                    safe_description,
                    safe_description,
                    hashlib.sha256(safe_description.encode()).hexdigest(),
                    observation_id,
                ),
            )
            con.execute(
                """
                UPDATE source_evidence
                SET excerpt=?, evidence_fingerprint=?
                WHERE observation_id=?
                """,
                (
                    safe_description,
                    hashlib.sha256(f"evidence:{safe_description}".encode()).hexdigest(),
                    observation_id,
                ),
            )

        # Licensed identities can be repeated in warning detail and secondary observation
        # fields. Apply the same deterministic map to every text-bearing column without
        # emitting or persisting the original values outside this temporary build process.
        tables = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        replacements = [
            (re.compile(re.escape(original), re.IGNORECASE), public_label)
            for original, public_label in anonymization_map.items()
            if original
        ]
        for table in tables:
            text_table_columns = [
                (row[1], str(row[2]).upper())
                for row in con.execute(f'PRAGMA table_info("{table}")')
            ]
            text_columns = [
                name
                for name, declared_type in text_table_columns
                if not declared_type
                or any(token in declared_type for token in ("TEXT", "CHAR", "CLOB", "JSON"))
            ]
            for column in text_columns:
                cell_rows = con.execute(
                    f'SELECT rowid, "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
                ).fetchall()
                for rowid, value in cell_rows:
                    if not isinstance(value, str):
                        continue
                    sanitized = value
                    for pattern, public_label in replacements:
                        sanitized = pattern.sub(public_label, sanitized)
                    if sanitized != value:
                        con.execute(
                            f'UPDATE "{table}" SET "{column}"=? WHERE rowid=?',
                            (sanitized, rowid),
                        )

        # Re-key source-level fingerprints after every sanitization step so the public
        # database does not retain equality-testable hashes derived from licensed values.
        for observation_id, field_name, raw_value, normalized_text in con.execute(
            "SELECT id, field_name, raw_value, normalized_text FROM source_observations"
        ).fetchall():
            fingerprint = hashlib.sha256(
                f"public-demo-observation:{observation_id}:{field_name}:{raw_value}:{normalized_text}".encode()
            ).hexdigest()
            con.execute(
                "UPDATE source_observations SET observation_fingerprint=? WHERE id=?",
                (fingerprint, observation_id),
            )
        for evidence_id, observation_id, excerpt in con.execute(
            "SELECT id, observation_id, excerpt FROM source_evidence"
        ).fetchall():
            fingerprint = hashlib.sha256(
                f"public-demo-evidence:{evidence_id}:{observation_id}:{excerpt}".encode()
            ).hexdigest()
            con.execute(
                "UPDATE source_evidence SET evidence_fingerprint=? WHERE id=?",
                (fingerprint, evidence_id),
            )

        # Config source paths are provenance metadata, but deployment images must not carry host paths.
        # Normalize both Windows and POSIX builders to the same public repository-relative form.
        for config_id, source_path in con.execute(
            "SELECT id, source_path FROM config_versions WHERE source_path IS NOT NULL"
        ).fetchall():
            filename = str(source_path).replace("\\", "/").rsplit("/", 1)[-1]
            con.execute(
                "UPDATE config_versions SET source_path=? WHERE id=?",
                (f"config/{filename}", config_id),
            )
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


def assert_seed_safe(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        dump = "\n".join(con.iterdump())
        source_contacts = con.execute(
            """
            SELECT COUNT(*)
            FROM source_observations so
            JOIN persons p ON p.id = so.person_id
            WHERE so.field_name='person.source_contact_row'
              AND (p.display_name NOT GLOB 'Source Contact [0-9][0-9]'
                   OR so.normalized_text NOT GLOB 'Source Contact [0-9][0-9]')
            """
        ).fetchone()[0]
        long_excerpts = con.execute(
            "SELECT COUNT(*) FROM source_evidence WHERE length(excerpt)>240"
        ).fetchone()[0]
    finally:
        con.close()
    failures = []
    if EMAIL_RE.search(dump):
        failures.append("direct email address remains in deployment seed")
    if PHONE_RE.search(dump):
        failures.append("direct phone number remains in deployment seed")
    if "/mnt/data" in dump or "context/private_source_documents" in dump:
        failures.append("private local source path remains in deployment seed")
    if WINDOWS_HOST_PATH_RE.search(dump):
        failures.append("Windows host path remains in deployment seed")
    if "Stafford-Technology-Campus-Phases-3-4.pdf" in dump or "EE-Reed-Construction-Houston-HQ.pdf" in dump:
        failures.append("private source filename remains in deployment seed")
    if source_contacts:
        failures.append("licensed-source-only contact identity remains in deployment seed")
    if long_excerpts:
        failures.append("unnecessary long source excerpt remains in deployment seed")
    if failures:
        raise RuntimeError("; ".join(failures))


def stamp_seed_migration_head(db_path: Path) -> str:
    """Bind a Base-created seed to the exact compatible Alembic head."""

    config = Config(str(ROOT / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if not head:
        raise RuntimeError("Alembic has no unique migration head")
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        con.execute("DELETE FROM alembic_version")
        con.execute("INSERT INTO alembic_version(version_num) VALUES (?)", (head,))
        con.commit()
    finally:
        con.close()
    return head


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
        migration_head = stamp_seed_migration_head(args.output)
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
    print(f"alembic_head={migration_head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
