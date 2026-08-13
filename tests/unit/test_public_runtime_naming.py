from __future__ import annotations

from scripts.validate_public_runtime_naming import (
    APPROVED_DESCRIPTION,
    APPROVED_TOPICS,
    PROFILE,
    validate_profile,
    validate_seed,
    validate_surfaces,
)


def test_shipped_runtime_and_current_public_docs_use_durable_names() -> None:
    assert validate_surfaces() == []


def test_seed_contains_no_legacy_runtime_identifiers_or_chronology() -> None:
    assert validate_seed() == []


def test_repository_profile_is_exact_and_privacy_safe() -> None:
    assert PROFILE.is_file()
    assert validate_profile() == []
    text = PROFILE.read_text(encoding="utf-8")
    assert APPROVED_DESCRIPTION in text
    assert all(topic in text for topic in APPROVED_TOPICS)
