from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.audit_public_data_boundary import (
    audit_database,
    audit_history,
    collect_private_source_tokens,
    tracked_inventory,
)
from scripts.build_demo_seed import assert_seed_safe, sanitize_seed

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data/demo_seed/offgrid_demo_seed.db"
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


def test_committed_seed_and_every_tracked_file_have_a_public_boundary_decision() -> None:
    assert_seed_safe(SEED)
    report = audit_database(SEED, {})
    assert report["result"] == "PASS"
    assert report["tables"] == 41  # 40 application tables plus Alembic's version binding
    assert report["classifications"]["C_private_source_contacts"] == {
        "rows": 32,
        "anonymized_rows": 32,
        "published_identity_rows": 0,
    }
    assert report["unmasked_contact_points"] == 0
    assert report["long_source_excerpts"] == 0
    assert report["private_document_sentinels_valid"] is True

    inventory, unresolved = tracked_inventory()
    assert inventory
    assert unresolved == []
    assert all(row["category"] != "REVIEW_REQUIRED" for row in inventory)


def test_seed_sanitizer_is_repeatable_without_collapsing_structural_rows(tmp_path: Path) -> None:
    candidate = tmp_path / "seed.db"
    shutil.copy2(SEED, candidate)
    sanitize_seed(candidate)
    assert_seed_safe(candidate)
    report = audit_database(candidate, {})
    assert report["result"] == "PASS"
    assert report["classifications"]["C_private_source_contacts"]["rows"] == 32


def test_private_source_comparison_records_counts_not_values() -> None:
    if not STAFFORD.is_file() or not EE_REED.is_file():
        pytest.skip("private source PDFs are intentionally absent from the public clone")
    tokens = collect_private_source_tokens(STAFFORD, EE_REED)
    report = audit_database(SEED, tokens)
    rendered = json.dumps(report).casefold()
    assert report["result"] == "PASS"
    assert report["private_comparison_hits"] == {
        "source_contact_identity": 0,
        "source_contact_channel": 0,
        "licensed_long_passage": 0,
        "source_content_hash": 0,
    }
    for values in tokens.values():
        assert all(value.decode(errors="ignore").casefold() not in rendered for value in values)


def test_history_audit_distinguishes_policy_references_from_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_name = b"licensed person example"
    monkeypatch.setattr(
        "scripts.audit_public_data_boundary.git_blob_contents",
        lambda: iter(
            [
                (".gitignore", b"context/private_source_documents/"),
                ("data/demo_seed/offgrid_demo_seed.db", private_name),
            ]
        ),
    )
    report = audit_history({"source_contact_identity": {private_name}}, set())
    assert report["result"] == "FAIL_REQUIRES_GOVERNED_HISTORY_DECISION"
    assert report["finding_counts"]["private_path_reference"] == 1
    assert report["finding_counts"]["source_contact_identity"] == 1
    assert report["errors"] == [
        "Git history contains 1 blob/path match(es) for source_contact_identity"
    ]
