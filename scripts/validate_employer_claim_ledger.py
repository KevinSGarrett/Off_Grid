"""Validate the private employer claim ledger and its controlled surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "release" / "FINAL_EMPLOYER_CLAIM_LEDGER.json"

VALID_CLASSIFICATIONS = {"EXPLICIT", "DERIVED", "VERIFIED", "INFERRED", "UNKNOWN"}
REQUIRED_CLAIM_IDS = {
    "STAFFORD_LOCATION",
    "STAFFORD_PROJECT_ID",
    "STAFFORD_STAGE",
    "STAFFORD_DATA_CENTER_NARRATIVE",
    "STAFFORD_EE_REED_GC",
    "STAFFORD_REPORTED_VALUE",
    "STAFFORD_VALUE_CAVEAT",
    "STAFFORD_FUTURE_ACTUAL_DATE",
    "EE_REED_HEADER_COUNTS",
    "EE_REED_SOURCE_PROJECT_ROWS",
    "EE_REED_CANONICAL_PROJECTS",
    "EE_REED_CONTACT_ROWS",
    "EE_REED_CONTACT_QUALITY",
    "EE_REED_MULTI_DOMAIN",
    "EE_REED_OPERATING_ENTITY_AMBIGUITY",
    "DOUG_EMPLOYMENT",
    "DOUG_STAFFORD_ASSOCIATION",
    "DOUG_ROLE_RELEVANCE",
    "DOUG_RENTAL_AUTHORITY",
    "PRODUCT_APPLICABILITY",
    "STAFFORD_COMMERCIAL_FIT",
    "STAFFORD_DATA_CONFIDENCE",
    "CRM_LEAD_READINESS",
    "CRM_DEAL_BLOCKED",
    "RENTAL_PROVIDER",
    "EXTERNAL_WRITES",
    "PRIMARY_KPI",
    "ASSESSMENT_COVERAGE",
    "COMMERCIAL_MOTIONS",
}

SURFACE_FILES = (
    "README.md",
    "apps/web/src/App.tsx",
    "apps/api/app/api/routes/contacts.py",
    "apps/api/app/reporting/metrics.py",
    "release/EMPLOYER_RESPONSE.md",
    "release/EXECUTIVE_BRIEF.md",
    "release/MONDAY_MORNING_BRIEF.md",
    "release/DEMO_PLAN.md",
    "release/FINAL_HANDOFF.md",
    "release/PRIVATE_INTERVIEW_QA.md",
    "release/SUBMISSION_MESSAGE_DRAFT.md",
)

SURFACE_REQUIRED_PHRASES = {
    "README.md": (
        "Promising candidate — VERIFY",
        "UNVERIFIED_APPLICABILITY",
        "Lead-ready / Deal-blocked",
        "System-Sourced Demos Booked",
    ),
    "apps/web/src/App.tsx": (
        "Evidence snapshot:",
        "UNKNOWN / unverified",
        "not a success probability",
    ),
    "release/EMPLOYER_RESPONSE.md": (
        "MEDIUM Data Confidence",
        "UNVERIFIED_APPLICABILITY",
        "rental authority remains UNKNOWN",
        "System-sourced demos booked",
    ),
    "release/EXECUTIVE_BRIEF.md": (
        "Data Confidence: **MEDIUM**",
        "Rental/equipment authority: **UNKNOWN",
        "N/A until production outcome history is connected",
    ),
    "release/MONDAY_MORNING_BRIEF.md": (
        "Data Confidence: MEDIUM",
        "UNVERIFIED_APPLICABILITY",
        "N/A",
    ),
    "release/DEMO_PLAN.md": (
        "UNKNOWN rental authority",
        "zero external writes",
        "No fabricated demos",
    ),
    "release/PRIVATE_INTERVIEW_QA.md": (
        "rental/equipment authority remains `UNKNOWN`",
        "KVT, KV6 and KVP remain",
        "N/A is not zero",
    ),
    "release/SUBMISSION_MESSAGE_DRAFT.md": (
        "MEDIUM Data Confidence",
        "product applicability remains unverified",
        "zero consequential external writes",
    ),
}


def load_ledger(path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_ledger(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return ["claims must be a list"]

    claim_rows: list[dict[str, Any]] = [claim for claim in claims if isinstance(claim, dict)]
    claim_ids = [str(claim.get("claim_id", "")) for claim in claim_rows]
    duplicates = sorted({claim_id for claim_id in claim_ids if claim_ids.count(claim_id) > 1})
    if duplicates:
        errors.append(f"duplicate claim IDs: {duplicates}")
    missing = sorted(REQUIRED_CLAIM_IDS - set(claim_ids))
    unexpected = sorted(set(claim_ids) - REQUIRED_CLAIM_IDS)
    if missing:
        errors.append(f"missing required claim IDs: {missing}")
    if unexpected:
        errors.append(f"unexpected claim IDs: {unexpected}")

    required_fields = {
        "claim_id",
        "claim_text",
        "evidence",
        "classification",
        "allowed_presentation",
        "forbidden_overstatement",
        "surfaces",
    }
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"claim[{index}] must be an object")
            continue
        claim_id = str(claim.get("claim_id", f"claim[{index}]"))
        absent = sorted(required_fields - set(claim))
        if absent:
            errors.append(f"{claim_id} missing fields: {absent}")
        if claim.get("classification") not in VALID_CLASSIFICATIONS:
            errors.append(f"{claim_id} has invalid classification")
        for list_field in ("evidence", "surfaces"):
            value = claim.get(list_field)
            if not isinstance(value, list) or not value:
                errors.append(f"{claim_id} requires non-empty {list_field}")
        for text_field in ("claim_text", "allowed_presentation", "forbidden_overstatement"):
            if not str(claim.get(text_field, "")).strip():
                errors.append(f"{claim_id} requires {text_field}")

    for claim_id in ("DOUG_EMPLOYMENT", "DOUG_STAFFORD_ASSOCIATION", "DOUG_ROLE_RELEVANCE"):
        current_claim = next((row for row in claim_rows if row.get("claim_id") == claim_id), None)
        evidence = " ".join(str(item) for item in (current_claim or {}).get("evidence", []))
        if "retrieved 2026-" not in evidence:
            errors.append(f"{claim_id} lacks a current retrieval timestamp")

    return errors


def validate_surfaces(root: Path, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    texts: dict[str, str] = {}
    for relative in SURFACE_FILES:
        path = root / relative
        if not path.is_file():
            errors.append(f"controlled surface missing: {relative}")
            continue
        texts[relative] = path.read_text(encoding="utf-8-sig")

    for relative, phrases in SURFACE_REQUIRED_PHRASES.items():
        folded = texts.get(relative, "").casefold()
        for phrase in phrases:
            if phrase.casefold() not in folded:
                errors.append(f"required employer claim missing in {relative}: {phrase}")

    forbidden = payload.get("global_forbidden_patterns", [])
    employer_text = "\n".join(texts.values()).casefold()
    for phrase in forbidden:
        if str(phrase).casefold() in employer_text:
            errors.append(f"forbidden employer overstatement found: {phrase}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    payload = load_ledger(args.ledger)
    errors = validate_ledger(payload) + validate_surfaces(args.root, payload)
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
