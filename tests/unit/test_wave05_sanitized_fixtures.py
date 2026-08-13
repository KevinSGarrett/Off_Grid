from pathlib import Path

import pytest

from scripts.audit_public_data_boundary import collect_private_source_tokens

ROOT = Path(__file__).resolve().parents[2]


def test_sanitized_fixtures_are_explicitly_synthetic_and_exclude_private_contacts() -> None:
    files = list((ROOT / "tests/golden/sanitized").glob("*.txt"))
    assert len(files) >= 2
    stafford = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
    ee_reed = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"
    if not stafford.is_file() or not ee_reed.is_file():
        pytest.skip("private comparison sources intentionally absent from public clone")
    tokens = collect_private_source_tokens(stafford, ee_reed)
    for path in files:
        text = path.read_text(encoding="utf-8").casefold().encode()
        assert b"sanitized" in text
        assert b"not a real source export" in text
        assert not any(value.lower() in text for values in tokens.values() for value in values)


def test_golden_expected_outputs_document_has_supported_format_claim() -> None:
    text = (ROOT / "tests/golden/GOLDEN_EXPECTED_OUTPUTS.md").read_text(encoding="utf-8")
    assert "Validated against the supplied Project and Company report formats; architecture supports additional adapters." in text
    assert "6 parsed / 6 expected" in text
    assert "87 / 87" in text
    assert "74 / 74" in text
