from __future__ import annotations

from pathlib import Path

import yaml

from app.products.registry import load_product_registry
from app.scoring.config import load_confidence_config, load_qualification_config

ROOT = Path(__file__).resolve().parents[2]


def test_qualification_and_confidence_configs_are_versioned_and_weighted() -> None:
    qualification = load_qualification_config()
    confidence = load_confidence_config()
    assert qualification.data["model"]["version"] == "qualification-2.0"
    assert confidence.data["model"]["version"] == "confidence-1.0"
    assert sum(float(x["max_points"]) for x in qualification.data["dimensions"]) == 100
    scoring_signals = [
        rule["signal"]
        for dimension in qualification.data["dimensions"]
        for rule in dimension["rules"]
    ]
    assert len(scoring_signals) == len(set(scoring_signals))
    assert "large_project_value" not in scoring_signals
    confidence_weight = sum(
        float(x["weight"])
        for section in ("observation_components", "relationship_components", "completeness_components")
        for x in confidence.data[section]
    )
    assert confidence_weight == 100


def test_product_registry_contains_only_controlled_products_and_fact_boundaries() -> None:
    registry = load_product_registry()
    assert registry.version == "products-2.1"
    assert {p.code for p in registry.products} == {"KVT", "KV6", "KVP"}
    for product in registry.products:
        assert product.approved_facts
        assert product.unknown_specifications
        assert all(f.source == "employer_assignment" for f in product.approved_facts)
        assert all(f.classification.value in {"EXPLICIT", "VERIFIED"} for f in product.approved_facts)


def test_scoring_runtime_has_no_stafford_or_external_id_special_case() -> None:
    paths = [
        ROOT / "apps/api/app/scoring",
        ROOT / "apps/api/app/products",
        ROOT / "config/qualification.yaml",
        ROOT / "config/products.yaml",
        ROOT / "config/trust_confidence.yaml",
    ]
    text = ""
    for path in paths:
        if path.is_dir():
            text += "\n".join(p.read_text(encoding="utf-8") for p in path.rglob("*.py"))
        else:
            text += path.read_text(encoding="utf-8")
    assert "1007341663" not in text
    assert "Stafford" not in text


def test_no_engineering_specification_or_roi_is_promoted_to_approved_fact() -> None:
    data = yaml.safe_load((ROOT / "config/products.yaml").read_text(encoding="utf-8"))
    forbidden = {x.lower() for x in data["registry"]["forbidden_inventions"]}
    approved = " ".join(
        fact["statement"].lower()
        for product in data["products"]
        for fact in product["approved_facts"]
    )
    # The approved statements are intentionally minimal; detailed spec concepts remain unknowns.
    for token in ("kwh", "kw ", "$", "% savings", "roi", "runtime hours", "units required"):
        assert token not in approved
    assert {"capacity", "runtime", "pricing", "roi", "quantity_required", "savings"} <= forbidden
