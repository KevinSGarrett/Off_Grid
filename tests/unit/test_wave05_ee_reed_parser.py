from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.ingestion.constructconnect_company import parse_company_report
from app.ingestion.normalization import email_domain
from app.ingestion.pdf_adapter import load_pdf

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"
EXPECTED = json.loads((ROOT / "tests/golden/ee_reed_expected.json").read_text(encoding="utf-8"))


def test_company_golden_counts_reconcile_exactly_from_real_pdf() -> None:
    payload = load_pdf(SOURCE)
    parsed = parse_company_report(payload)
    counts = EXPECTED["expected_counts"]
    assert len(payload.sha256) == 64
    assert parsed.company_id == EXPECTED["company_id"]
    assert parsed.company_name == EXPECTED["company_name"]
    assert len(parsed.planning_rows) == counts["planning"] == parsed.planning_projects
    assert len(parsed.post_bid_rows) == counts["post_bid"] == parsed.post_bid_projects
    assert len(parsed.bidding_role_rows) == counts["bidding_role"] == parsed.bidding_role_projects
    assert len(parsed.contacts) == counts["contacts"]
    assert len(parsed.planning_rows) + len(parsed.post_bid_rows) + len(parsed.bidding_role_rows) == counts["project_rows_total"]
    assert parsed.reconciliation.passed


def test_company_parser_finds_stafford_phase_rows_and_contact_quality_cases() -> None:
    parsed = parse_company_report(load_pdf(SOURCE))
    projects = [*parsed.planning_rows, *parsed.post_bid_rows, *parsed.bidding_role_rows]
    stafford = {row.project_name: row for row in projects if row.project_name.startswith("Stafford Technology Campus")}
    for expected in EXPECTED["stafford_rows"]:
        row = stafford[expected["name"]]
        assert int(row.value or 0) == expected["value_usd"]
        assert row.page == expected["page"]

    names = Counter(row.name for row in parsed.contacts)
    recurrence = sorted(names.values(), reverse=True)
    cases = EXPECTED["required_contact_cases"]
    assert recurrence[0] == cases["maximum_exact_name_recurrence"]
    assert cases["secondary_exact_name_recurrence"] in recurrence
    assert sum(1 for row in parsed.contacts if row.email and row.email.lower().startswith("info@")) >= cases["minimum_generic_named_inboxes"]
    domains = {email_domain(row.email) for row in parsed.contacts if row.email}
    assert set(EXPECTED["required_domains"]) <= domains
