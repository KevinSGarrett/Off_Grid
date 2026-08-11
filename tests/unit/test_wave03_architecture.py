from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _yaml(rel: str):
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


def test_every_requirement_has_architecture_allocation() -> None:
    reqs = _yaml("project/requirements.yaml")["requirements"]
    architecture = _yaml("project/architecture_map.yaml")
    mappings = architecture["mappings"]
    assert architecture["requirements_baseline"] == "W02-2026-08-10"
    assert architecture["architecture_version"] == "ARCH-0.3.0"
    assert {r["id"] for r in reqs} == {m["requirement_id"] for m in mappings}
    assert len(mappings) == len(reqs) == 180


def test_architecture_mappings_reference_known_components() -> None:
    component_ids = {c["id"] for c in _yaml("project/component_catalog.yaml")["components"]}
    for mapping in _yaml("project/architecture_map.yaml")["mappings"]:
        assert mapping["components"]
        assert set(mapping["components"]) <= component_ids


def test_required_wave03_docs_and_adrs_exist_and_are_nonempty() -> None:
    required = [
        "docs/ARCHITECTURE.md",
        "docs/COMPONENT_BOUNDARIES.md",
        "docs/DATA_FLOW.md",
        "docs/STATE_MACHINES.md",
        "docs/ERROR_HANDLING.md",
        "docs/SECURITY_BOUNDARIES.md",
        "docs/AI_BOUNDARIES.md",
        "docs/API_SURFACE_BLUEPRINT.md",
        "docs/DEPLOYMENT_TOPOLOGY_BASELINE.md",
        "docs/ARCHITECTURE_REQUIREMENT_COVERAGE.md",
    ]
    for rel in required:
        path = ROOT / rel
        assert path.exists(), rel
        assert path.stat().st_size > 400, rel
    adrs = sorted((ROOT / "docs/adr").glob("ADR-*.md"))
    assert len(adrs) >= 10
    assert all(p.stat().st_size > 350 for p in adrs)


def test_diagram_sources_cover_key_boundaries() -> None:
    expected = {
        "system_context.mmd",
        "component_architecture.mmd",
        "ingestion_pipeline.mmd",
        "project_state_machine.mmd",
        "contact_state_machine.mmd",
        "crm_promotion.mmd",
        "dual_commercial_motion.mmd",
        "security_boundaries.mmd",
        "ai_grounding_flow.mmd",
        "error_exception_flow.mmd",
    }
    actual = {p.name for p in (ROOT / "docs/diagrams").glob("*.mmd")}
    assert expected <= actual


def test_pure_domain_modules_do_not_import_framework_or_vendor_sdks() -> None:
    forbidden = ("fastapi", "sqlalchemy", "openai", "pipedrive", "apollo", "boto3")
    for path in (ROOT / "apps/api/app/domain").glob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for name in forbidden:
            assert f"import {name}" not in source
            assert f"from {name}" not in source
