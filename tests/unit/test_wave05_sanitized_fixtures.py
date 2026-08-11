from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sanitized_fixtures_are_explicitly_synthetic_and_exclude_known_real_contacts() -> None:
    files = list((ROOT / "tests/golden/sanitized").glob("*.txt"))
    assert len(files) >= 2
    forbidden = ["Curtis Rakosi", "Curits Rakosi", "Dan Delforge", "Brian Owrey", "cbrown@eereedeast.com"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "SANITIZED" in text
        assert "NOT A REAL SOURCE EXPORT" in text
        assert not any(value in text for value in forbidden)


def test_golden_expected_outputs_document_has_supported_format_claim() -> None:
    text = (ROOT / "tests/golden/GOLDEN_EXPECTED_OUTPUTS.md").read_text(encoding="utf-8")
    assert "Validated against the supplied Project and Company report formats; architecture supports additional adapters." in text
    assert "6 parsed / 6 expected" in text
    assert "87 / 87" in text
    assert "74 / 74" in text
