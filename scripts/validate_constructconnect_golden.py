#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

from app.ingestion.constructconnect_company import parse_company_report  # noqa: E402
from app.ingestion.constructconnect_project import parse_project_report  # noqa: E402
from app.ingestion.pdf_adapter import load_pdf  # noqa: E402


def main() -> int:
    stafford_path = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
    ee_path = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"
    stafford_payload = load_pdf(stafford_path)
    stafford = parse_project_report(stafford_payload)
    ee_payload = load_pdf(ee_path)
    ee = parse_company_report(ee_payload)
    result = {
        "parser_version": "constructconnect-pdf-0.5.0",
        "supported_format_claim": "Validated against the supplied Project and Company report formats; architecture supports additional adapters.",
        "stafford": {
            "sha256": stafford_payload.sha256,
            "project_id": stafford.project_id,
            "project_name": stafford.project_name,
            "value": str(stafford.estimated_value),
            "stage": stafford.stage,
            "report_date": stafford.report_date.isoformat(),
            "start_date": stafford.start_date.isoformat() if stafford.start_date else None,
            "start_date_label": stafford.start_date_label,
            "design_team_rows": len(stafford.design_team),
        },
        "ee_reed": {
            "sha256": ee_payload.sha256,
            "company_id": ee.company_id,
            "planning": len(ee.planning_rows),
            "post_bid": len(ee.post_bid_rows),
            "bidding_role": len(ee.bidding_role_rows),
            "contacts": len(ee.contacts),
            "reconciliation_passed": ee.reconciliation.passed,
        },
    }
    print(json.dumps(result, indent=2))
    return 0 if ee.reconciliation.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
