#!/usr/bin/env python3
"""Audit the committed demo seed, tracked tree, and optional full Git history.

The report records counts, classifications, hashes, and paths that are already
public. Private comparison values are held only in memory and are never emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

EMAIL_RE = re.compile(rb"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(rb"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
PRIVATE_PATH_RE = re.compile(
    rb"(?:context[/\\]private_source_documents|[A-Z]:[/\\]Users[/\\]|/mnt/data|Chat_Logs)",
    re.IGNORECASE,
)
PRIVATE_FILENAME_RE = re.compile(
    rb"(?:Stafford-Technology-Campus-Phases-3-4|EE-Reed-Construction-Houston-HQ)\.pdf",
    re.IGNORECASE,
)
SECRET_RE = re.compile(
    rb"(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16})",
    re.IGNORECASE,
)
PUBLIC_SOURCE_SENTINEL_RE = re.compile(r"private-source-[0-9]{2}\.pdf")
PRIVATE_ENV_NAMES = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "OPENAI_API_KEY",
    "APOLLO_API_KEY",
    "PIPEDRIVE_API_TOKEN",
    "JIRA_API_KEY",
    "APP_ACCESS_PASSWORD",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run_git(*args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        input=input_bytes,
        capture_output=True,
        check=True,
        timeout=180,
    ).stdout


def tracked_file_decision(path: str) -> tuple[str, str]:
    lower = path.lower()
    if lower == "data/demo_seed/offgrid_demo_seed.db":
        return (
            "PUBLIC_SANITIZED_RUNTIME_FIXTURE",
            "Required for reproducible sanitized demo startup; contents must pass this audit.",
        )
    if lower == ".env.example":
        return (
            "PUBLIC_CONFIGURATION_TEMPLATE",
            "Documents variable names and safe placeholder values; live .env files remain ignored.",
        )
    if lower.startswith((".github/", "infra/")) or lower in {
        ".dockerignore",
        ".gitattributes",
        ".gitignore",
        "dockerfile",
        "makefile",
    }:
        return "PUBLIC_RELEASE_GOVERNANCE", "Required to reproduce and review CI, deployment, or publication safety."
    if lower.startswith(("apps/", "docker/", "migrations/", "scripts/", "alembic")) or lower in {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "requirements.lock",
    }:
        return "PUBLIC_IMPLEMENTATION", "Application or reproducibility implementation reviewed by the employer."
    if lower.startswith(("tests/", "config/", "project/")):
        return "PUBLIC_SANITIZED_VERIFICATION", "Sanitized contract, configuration, or automated validation evidence."
    if lower.startswith(("assets/readme/", "release/")) or lower.endswith((".md", ".rst")):
        return "PUBLIC_DOCUMENTATION", "Reviewer-facing operation, security, design, or release documentation."
    return "REVIEW_REQUIRED", "No approved public-benefit category matched this path."


def tracked_inventory() -> tuple[list[dict[str, str]], list[str]]:
    paths = [item.decode() for item in run_git("ls-files", "-z").split(b"\0") if item]
    inventory: list[dict[str, str]] = []
    unresolved: list[str] = []
    for path in paths:
        category, rationale = tracked_file_decision(path)
        inventory.append({"path": path, "category": category, "public_rationale": rationale})
        if category == "REVIEW_REQUIRED":
            unresolved.append(path)
    return inventory, unresolved


def audit_tracked_content(private_tokens: dict[str, set[bytes]]) -> dict[str, object]:
    paths = [item.decode() for item in run_git("ls-files", "-z").split(b"\0") if item]
    findings: Counter[str] = Counter()
    affected_paths: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        candidate = ROOT / path
        if not candidate.is_file():
            continue
        content = candidate.read_bytes()
        lower = content.lower()
        if SECRET_RE.search(content):
            findings["credential_pattern"] += 1
            affected_paths["credential_pattern"].add(sha256_bytes(path.encode()))
        for category, values in private_tokens.items():
            if any(value.lower() in lower for value in values):
                findings[category] += 1
                affected_paths[category].add(sha256_bytes(path.encode()))
    errors = [
        f"current tracked tree contains {count} file match(es) for {category}"
        for category, count in sorted(findings.items())
    ]
    return {
        "files_scanned": len(paths),
        "finding_counts": dict(sorted(findings.items())),
        "affected_path_hashes": {
            category: sorted(values) for category, values in sorted(affected_paths.items())
        },
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def sqlite_text_inventory(connection: sqlite3.Connection) -> list[dict[str, object]]:
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    result: list[dict[str, object]] = []
    for table in tables:
        columns = [(row[1], str(row[2]).upper()) for row in connection.execute(f'PRAGMA table_info("{table}")')]
        text_columns = [
            name
            for name, declared_type in columns
            if not declared_type or any(token in declared_type for token in ("TEXT", "CHAR", "CLOB", "JSON"))
        ]
        nonempty = {
            column: int(
                connection.execute(
                    f'SELECT COUNT(*) FROM "{table}" '
                    f'WHERE "{column}" IS NOT NULL AND TRIM(CAST("{column}" AS TEXT)) <> \'\''
                ).fetchone()[0]
            )
            for column in text_columns
        }
        result.append(
            {
                "table": table,
                "rows": int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]),
                "text_columns": text_columns,
                "nonempty_text_counts": nonempty,
            }
        )
    return result


def audit_database(path: Path, private_tokens: dict[str, set[bytes]]) -> dict[str, object]:
    display_path = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
    connection = sqlite3.connect(path)
    try:
        dump = "\n".join(connection.iterdump()).encode()
        lower_dump = dump.lower()
        inventory = sqlite_text_inventory(connection)
        source_contact_rows = int(
            connection.execute(
                "SELECT COUNT(*) FROM source_observations WHERE field_name='person.source_contact_row'"
            ).fetchone()[0]
        )
        anonymized_source_contacts = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM source_observations so
                JOIN persons p ON p.id=so.person_id
                WHERE so.field_name='person.source_contact_row'
                  AND p.display_name GLOB 'Source Contact [0-9][0-9]'
                  AND so.normalized_text GLOB 'Source Contact [0-9][0-9]'
                """
            ).fetchone()[0]
        )
        public_evidence_people = int(
            connection.execute(
                "SELECT COUNT(DISTINCT person_id) FROM external_evidence WHERE person_id IS NOT NULL"
            ).fetchone()[0]
        )
        unmasked_contacts = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM person_contact_points
                WHERE value NOT GLOB '[[]masked-*' OR normalized_value NOT GLOB '[[]masked-*'
                """
            ).fetchone()[0]
        )
        long_excerpts = int(
            connection.execute("SELECT COUNT(*) FROM source_evidence WHERE length(excerpt)>240").fetchone()[0]
        )
        documents = connection.execute(
            "SELECT original_filename, content_sha256, blob_ref, is_private FROM source_documents ORDER BY original_filename"
        ).fetchall()
        document_sentinels_valid = all(
            PUBLIC_SOURCE_SENTINEL_RE.fullmatch(str(filename))
            and str(blob_ref) == "private-source-not-packaged"
            and int(is_private) == 1
            and str(content_hash)
            == hashlib.sha256(
                f"offgrid-public-demo:{Path(str(filename)).stem}:not-distributed".encode()
            ).hexdigest()
            for filename, content_hash, blob_ref, is_private in documents
        )
    finally:
        connection.close()

    pattern_hits = {
        "direct_email": len(EMAIL_RE.findall(dump)),
        "direct_phone": len(PHONE_RE.findall(dump)),
        "private_path": len(PRIVATE_PATH_RE.findall(dump)),
        "private_document_filename": len(PRIVATE_FILENAME_RE.findall(dump)),
        "credential_pattern": len(SECRET_RE.findall(dump)),
    }
    private_hits = {
        category: sum(lower_dump.count(token.lower()) for token in values)
        for category, values in private_tokens.items()
    }
    errors: list[str] = []
    errors.extend(f"database contains {count} {label} match(es)" for label, count in pattern_hits.items() if count)
    errors.extend(f"database contains {count} private {label} match(es)" for label, count in private_hits.items() if count)
    if source_contact_rows != anonymized_source_contacts:
        errors.append("not every private source-directory contact is anonymized")
    if unmasked_contacts:
        errors.append("unmasked person contact point remains")
    if long_excerpts:
        errors.append("source evidence contains excerpts longer than 240 characters")
    if not document_sentinels_valid:
        errors.append("private source-document metadata is not a valid public sentinel")
    return {
        "path": display_path,
        "sha256": sha256_bytes(path.read_bytes()),
        "bytes": path.stat().st_size,
        "tables": len(inventory),
        "text_inventory": inventory,
        "classifications": {
            "A_public_project_context": {
                "canonical_projects": next(row["rows"] for row in inventory if row["table"] == "projects"),
                "source_fact_observations": next(row["rows"] for row in inventory if row["table"] == "source_observations") - source_contact_rows,
            },
            "B_publicly_researched_people": public_evidence_people,
            "C_private_source_contacts": {
                "rows": source_contact_rows,
                "anonymized_rows": anonymized_source_contacts,
                "published_identity_rows": source_contact_rows - anonymized_source_contacts,
            },
        },
        "pattern_hits": pattern_hits,
        "private_comparison_hits": private_hits,
        "unmasked_contact_points": unmasked_contacts,
        "long_source_excerpts": long_excerpts,
        "private_document_sentinels_valid": document_sentinels_valid,
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def load_env_secrets(path: Path | None) -> set[bytes]:
    if path is None or not path.is_file():
        return set()
    values: set[bytes] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        if key.strip().upper() not in PRIVATE_ENV_NAMES:
            continue
        value = raw.strip().strip("\"'")
        if len(value) >= 8 and not any(marker in value.lower() for marker in ("change-me", "example", "placeholder")):
            values.add(value.encode())
    return values


def collect_private_source_tokens(stafford: Path, ee_reed: Path) -> dict[str, set[bytes]]:
    if not stafford.is_file() or not ee_reed.is_file():
        raise FileNotFoundError("both private source PDFs are required for the comparison scan")
    from app.demo.bootstrap import build_real_demo_database

    with tempfile.TemporaryDirectory(prefix="offgrid-private-comparison-") as temporary:
        database = Path(temporary) / "raw.db"
        build_real_demo_database(
            database_path=database,
            stafford_pdf=stafford,
            ee_reed_pdf=ee_reed,
            reset=True,
        )
        connection = sqlite3.connect(database)
        try:
            names = {
                str(row[0]).casefold().encode()
                for row in connection.execute(
                    """
                    SELECT DISTINCT p.display_name
                    FROM persons p
                    JOIN source_observations so ON so.person_id=p.id
                    WHERE so.field_name='person.source_contact_row'
                    """
                )
                if row[0] and len(str(row[0]).strip()) >= 5
            }
            channels = {
                str(row[0]).casefold().encode()
                for row in connection.execute(
                    "SELECT DISTINCT value FROM person_contact_points WHERE value IS NOT NULL"
                )
                if row[0] and not str(row[0]).startswith("[masked-") and len(str(row[0]).strip()) >= 5
            }
            long_passages = {
                str(row[0]).casefold().encode()
                for row in connection.execute(
                    "SELECT raw_value FROM source_observations WHERE length(raw_value)>240"
                )
                if row[0]
            }
            source_hashes = {
                str(row[0]).casefold().encode()
                for row in connection.execute(
                    "SELECT content_sha256 FROM source_documents WHERE content_sha256 IS NOT NULL"
                )
                if row[0]
            }
        finally:
            connection.close()
    return {
        "source_contact_identity": names,
        "source_contact_channel": channels,
        "licensed_long_passage": long_passages,
        "source_content_hash": source_hashes,
    }


def git_blob_contents() -> Iterable[tuple[str, bytes]]:
    object_lines = run_git("rev-list", "--objects", "--all").decode(errors="replace").splitlines()
    object_paths: dict[str, set[str]] = defaultdict(set)
    for line in object_lines:
        object_id, _, path = line.partition(" ")
        if path:
            object_paths[object_id].add(path)
    object_ids = sorted(object_paths)
    if not object_ids:
        return
    payload = ("\n".join(object_ids) + "\n").encode()
    batch = run_git("cat-file", "--batch", input_bytes=payload)
    offset = 0
    for object_id in object_ids:
        line_end = batch.index(b"\n", offset)
        header = batch[offset:line_end].decode(errors="replace").split()
        offset = line_end + 1
        if len(header) < 3 or header[1] != "blob":
            continue
        size = int(header[2])
        content = batch[offset : offset + size]
        offset += size + 1
        for path in object_paths[object_id]:
            yield path, content


def audit_history(private_tokens: dict[str, set[bytes]], secret_values: set[bytes]) -> dict[str, object]:
    finding_counts: Counter[str] = Counter()
    affected_blobs: set[str] = set()
    affected_paths: set[str] = set()
    blobs_scanned = 0
    for path, content in git_blob_contents():
        blobs_scanned += 1
        lower = content.lower()
        categories: set[str] = set()
        if PRIVATE_PATH_RE.search(content):
            categories.add("private_path_reference")
        if PRIVATE_FILENAME_RE.search(content):
            categories.add("private_document_filename_reference")
        if SECRET_RE.search(content):
            categories.add("credential_pattern")
        if path.lower().endswith((".pdf", ".zip")) or "private_source_documents" in path.lower():
            categories.add("forbidden_history_path")
        for category, values in private_tokens.items():
            if any(value.lower() in lower for value in values):
                categories.add(category)
        if any(value in content for value in secret_values):
            categories.add("configured_secret_value")
        if categories:
            path_hash = sha256_bytes(path.encode())
            affected_paths.add(path_hash)
            affected_blobs.add(sha256_bytes(content))
            finding_counts.update(categories)
    blocking_categories = {
        "configured_secret_value",
        "credential_pattern",
        "forbidden_history_path",
        "licensed_long_passage",
        "source_contact_channel",
        "source_contact_identity",
        "source_content_hash",
    }
    errors = [
        f"Git history contains {count} blob/path match(es) for {category}"
        for category, count in sorted(finding_counts.items())
        if category in blocking_categories
    ]
    return {
        "blobs_and_paths_scanned": blobs_scanned,
        "finding_counts": dict(sorted(finding_counts.items())),
        "blocking_categories": sorted(blocking_categories),
        "reference_only_categories": [
            "private_document_filename_reference",
            "private_path_reference",
        ],
        "affected_blob_content_hashes": sorted(affected_blobs),
        "affected_path_hashes": sorted(affected_paths),
        "destructive_history_rewrite_performed": False,
        "result": "PASS" if not errors else "FAIL_REQUIRES_GOVERNED_HISTORY_DECISION",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "data/demo_seed/offgrid_demo_seed.db")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scan-history", action="store_true")
    parser.add_argument("--scan-private-sources", action="store_true")
    parser.add_argument("--stafford", type=Path, default=ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf")
    parser.add_argument("--ee-reed", type=Path, default=ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()

    private_tokens: dict[str, set[bytes]] = {}
    if args.scan_private_sources:
        private_tokens = collect_private_source_tokens(args.stafford, args.ee_reed)
    inventory, unresolved = tracked_inventory()
    database = audit_database(args.database, private_tokens)
    tracked_content = audit_tracked_content(private_tokens)
    history = (
        audit_history(private_tokens, load_env_secrets(args.env_file))
        if args.scan_history
        else {"result": "NOT_REQUESTED", "destructive_history_rewrite_performed": False}
    )
    errors = list(database["errors"])
    errors.extend(f"tracked file requires public/private decision: {path}" for path in unresolved)
    errors.extend(tracked_content["errors"])
    if history["result"] not in {"PASS", "NOT_REQUESTED"}:
        errors.extend(history["errors"])
    report = {
        "schema_version": "offgrid-public-data-boundary-audit-1.0",
        "database": database,
        "tracked_tree": {
            "files": len(inventory),
            "category_counts": dict(sorted(Counter(row["category"] for row in inventory).items())),
            "unresolved_files": unresolved,
            "inventory": inventory,
            "content_scan": tracked_content,
            "result": "PASS" if not unresolved and tracked_content["result"] == "PASS" else "FAIL",
        },
        "private_comparison": {
            "performed": args.scan_private_sources,
            "token_counts": {key: len(value) for key, value in private_tokens.items()},
            "values_recorded": False,
        },
        "git_history": history,
        "secrets_recorded": False,
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, args.output)
    print(
        json.dumps(
            {
                "result": report["result"],
                "database": database["result"],
                "tracked_tree": report["tracked_tree"]["result"],
                "history": history["result"],
                "tracked_files": len(inventory),
                "private_values_recorded": False,
                "errors": errors,
            },
            indent=2,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
