from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from app.ingestion.errors import MalformedPDFError, UnsupportedReportError
from app.ingestion.pdf_adapter import detect_report_type, load_pdf

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


def test_supplied_report_formats_are_detected() -> None:
    assert detect_report_type(load_pdf(STAFFORD)) == "PROJECT"
    assert detect_report_type(load_pdf(EE_REED)) == "COMPANY"


def test_non_pdf_is_rejected_as_malformed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(MalformedPDFError, match="PDF header"):
        load_pdf(bad)


def test_readable_but_unknown_pdf_is_rejected_with_accurate_scope_claim(tmp_path: Path) -> None:
    path = tmp_path / "unknown.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Some unrelated construction report")
    doc.save(path)
    with pytest.raises(UnsupportedReportError, match="Validated against the supplied Project and Company report formats"):
        detect_report_type(load_pdf(path))
