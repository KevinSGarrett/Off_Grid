from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_employer_claim_ledger import (
    DEFAULT_LEDGER,
    REQUIRED_CLAIM_IDS,
    load_ledger,
    validate_ledger,
    validate_surfaces,
)

ROOT = Path(__file__).resolve().parents[2]


def _valid_claim(claim_id: str) -> dict[str, object]:
    evidence = ["source retrieved 2026-08-13T03:17:41Z"]
    return {
        "claim_id": claim_id,
        "claim_text": "Bounded claim",
        "evidence": evidence,
        "classification": "DERIVED",
        "allowed_presentation": "Bounded wording",
        "forbidden_overstatement": "Stronger wording",
        "surfaces": ["API"],
    }


def test_claim_ledger_schema_rejects_missing_and_duplicate_claims() -> None:
    payload = {"claims": [_valid_claim(claim_id) for claim_id in sorted(REQUIRED_CLAIM_IDS)]}
    assert validate_ledger(payload) == []

    payload["claims"].append(_valid_claim("STAFFORD_LOCATION"))
    errors = validate_ledger(payload)
    assert any("duplicate claim IDs" in error for error in errors)


def test_private_final_claim_ledger_and_controlled_surfaces_pass_when_available() -> None:
    if not DEFAULT_LEDGER.is_file():
        pytest.skip("Private final-submission claim ledger is intentionally outside public Git")
    payload = load_ledger(DEFAULT_LEDGER)
    assert validate_ledger(payload) == []
    assert validate_surfaces(ROOT, payload) == []


def test_contact_verification_surface_exposes_snapshot_time(wave14_full_state) -> None:
    project_id = wave14_full_state["ids"]["project"]
    response = wave14_full_state["client"].get(
        f"/api/v1/projects/{project_id}/contact-candidates"
    )
    assert response.status_code == 200
    dated = [
        item["verification"]["assessed_at"]
        for item in response.json()["items"]
        if item["verification"] is not None
    ]
    assert dated and all(
        value.startswith("2026-08-10T") and value.endswith("+00:00") for value in dated
    )

    app = (ROOT / "apps/web/src/App.tsx").read_text(encoding="utf-8")
    types = (ROOT / "apps/web/src/types.ts").read_text(encoding="utf-8")
    assert "Evidence snapshot:" in app
    assert "Snapshot-dated evidence" in app
    assert "assessed_at?: string" in types
