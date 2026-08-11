from __future__ import annotations

import json
from pathlib import Path

from app.ingestion.constructconnect_project import parse_project_report
from app.ingestion.pdf_adapter import load_pdf

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EXPECTED = json.loads((ROOT / "tests/golden/stafford_expected.json").read_text(encoding="utf-8"))


def test_stafford_golden_fields_are_parsed_from_real_pdf() -> None:
    payload = load_pdf(SOURCE)
    parsed = parse_project_report(payload)
    assert payload.sha256 == EXPECTED["source_sha256"]
    assert parsed.project_id == EXPECTED["project_id"]
    assert parsed.project_name == EXPECTED["project_name"]
    assert int(parsed.estimated_value or 0) == EXPECTED["reported_value_usd"]
    assert parsed.stage == EXPECTED["stage"]
    assert parsed.city == EXPECTED["city"]
    assert parsed.region == EXPECTED["region"]
    assert parsed.start_date.isoformat() == EXPECTED["start_date"]
    assert parsed.start_date_label == EXPECTED["start_date_label"]
    assert parsed.report_date.date().isoformat() == EXPECTED["report_date"]
    assert parsed.currently_tracked is False
    scope = (parsed.scope or "").lower()
    assert all(signal in scope for signal in EXPECTED["scope_signals"])


def test_stafford_design_team_contains_source_gc_owner_developer() -> None:
    parsed = parse_project_report(load_pdf(SOURCE))
    role_to_company = {row.role: row.company_name for row in parsed.design_team}
    assert role_to_company["General Contractor"] == EXPECTED["general_contractor"]
    assert role_to_company["Owner"] == EXPECTED["owner"]
    assert role_to_company["Developer"] == EXPECTED["developer"]
    assert len(parsed.design_team) == 6
    civil = next(row for row in parsed.design_team if row.role == "Civil Engineer")
    assert civil.contact_name == "Mike O'Shaughnessy"
