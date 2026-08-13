from __future__ import annotations

import shutil
import sqlite3
import hashlib
from pathlib import Path

from scripts.build_demo_seed import assert_seed_safe, sanitize_seed, stamp_seed_migration_head
from scripts.verify_demo_seed_coherence import DEFAULT_SEED, migration_head, verify


def test_committed_seed_matches_schema_config_services_and_restore_contract() -> None:
    before = hashlib.sha256(DEFAULT_SEED.read_bytes()).hexdigest()
    report = verify(DEFAULT_SEED)
    after = hashlib.sha256(DEFAULT_SEED.read_bytes()).hexdigest()
    assert report["status"] == "PASS", report["errors"]
    assert before == after == report["seed"]["sha256"]
    assert report["schemas"] == {
        "seed_model_match": True,
        "empty_migration_model_match": True,
        "prebuilt_upgrade_model_match": True,
    }
    assert report["read_only_restore"]["identical"] is True
    assert report["services"]["before_counts"] == report["services"]["after_counts"]
    assert report["services"]["stafford"]["product_applicability"] == {
        "KVT": "UNVERIFIED_APPLICABILITY",
        "KV6": "UNVERIFIED_APPLICABILITY",
        "KVP": "UNVERIFIED_APPLICABILITY",
    }


def test_seed_sanitizer_normalizes_host_paths_and_stamps_current_head(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.db"
    shutil.copy2(DEFAULT_SEED, candidate)
    connection = sqlite3.connect(candidate)
    try:
        connection.execute(
            "UPDATE config_versions SET source_path='C:\\Off_Grid\\config\\qualification.yaml' "
            "WHERE config_kind='qualification'"
        )
        connection.execute("DELETE FROM alembic_version")
        connection.commit()
    finally:
        connection.close()

    assert stamp_seed_migration_head(candidate) == migration_head()
    sanitize_seed(candidate)
    assert_seed_safe(candidate)
    connection = sqlite3.connect(candidate)
    try:
        paths = [row[0] for row in connection.execute("SELECT source_path FROM config_versions")]
        versions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    finally:
        connection.close()
    assert all(path.startswith("config/") and "\\" not in path for path in paths)
    assert versions == [migration_head()]
