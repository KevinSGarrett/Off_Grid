from __future__ import annotations

from app.contact_resolution.config import load_contact_resolution_configs
from app.contact_resolution.policy import SourcePrecedencePolicy
from app.domain.states import VerificationState


def test_contact_resolution_configuration_is_versioned_and_weights_total_100() -> None:
    cfg = load_contact_resolution_configs()
    assert cfg.contact.data["model"]["version"] == "contact-resolution-1.0"
    assert sum(cfg.contact.data["score_weights"].values()) == 100
    assert cfg.personas.data["registry"]["version"] == "personas-1.0"
    assert cfg.precedence.data["policy"]["version"] == "source-precedence-1.0"


def test_source_precedence_is_attribute_specific_and_rental_authority_is_fail_closed() -> None:
    policy = SourcePrecedencePolicy()
    employer_role = policy.rule_for("role_relevance", "EMPLOYER_OFFICIAL_PROFILE")
    employer_authority = policy.rule_for("rental_authority", "EMPLOYER_OFFICIAL_PROFILE")
    first_party_project = policy.rule_for("project_association", "FIRST_PARTY_PROJECT_POST")
    assert employer_role.max_state is VerificationState.VERIFIED
    assert employer_authority.max_state is VerificationState.SUPPORTED
    assert first_party_project.max_state is VerificationState.VERIFIED
    assert policy.cap_state(VerificationState.VERIFIED, employer_authority.max_state) is VerificationState.SUPPORTED


def test_personas_are_investigation_targets_not_authority_assertions() -> None:
    cfg = load_contact_resolution_configs().personas.data
    assert all("authority" not in row["key"] for row in cfg["personas"])
    assert "never verifies project association or rental authority" in cfg["registry"]["rule"]


def test_public_research_snapshot_records_no_prospect_outreach_or_live_apollo() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    snapshot = json.loads((root / "research/WAVE_08_PUBLIC_RESEARCH_SNAPSHOT.json").read_text())
    unknowns = " ".join(snapshot["explicit_unknowns"])
    assert "No prospect was contacted" in unknowns
    assert "No Apollo live search or enrichment call was executed" in unknowns
