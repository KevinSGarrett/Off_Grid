from __future__ import annotations

from scripts.release_claims import CURRENT_CLAIM_RULES, validate_current_claims


def test_current_claim_rules_accept_required_and_reject_stale_phrases():
    valid = {
        name: ("\n".join(rules["required"]) + "\n").encode()
        for name, rules in CURRENT_CLAIM_RULES.items()
    }
    assert validate_current_claims(valid) == []

    for name, rules in CURRENT_CLAIM_RULES.items():
        for phrase in rules["forbidden"]:
            stale = dict(valid)
            stale[name] += (phrase + "\n").encode()
            errors = validate_current_claims(stale)
            assert any(
                "stale current claim" in error and phrase in error for error in errors
            )

        missing = dict(valid)
        missing[name] = b""
        errors = validate_current_claims(missing)
        assert any("current claim missing" in error for error in errors)
