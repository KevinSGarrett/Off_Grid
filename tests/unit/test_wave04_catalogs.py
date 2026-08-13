from __future__ import annotations

from pathlib import Path

import yaml

from app.domain.states import ConfidenceState, PIIClass, ValidationState
from app.models import Base


def load_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def test_data_model_catalog_matches_registered_schema() -> None:
    catalog = load_yaml("project/data_model_catalog.yaml")
    assert catalog["schema_version"] == "DATA-0.4.2"
    assert catalog["table_count"] == len(Base.metadata.tables) == 40
    assert {item["table"] for item in catalog["tables"]} == set(Base.metadata.tables)


def test_trust_catalog_matches_code_enums() -> None:
    catalog = load_yaml("project/trust_state_matrix.yaml")
    assert set(catalog["validation_states"]) == {state.value for state in ValidationState}
    assert set(catalog["confidence_states"]) == {state.value for state in ConfidenceState}


def test_privacy_catalog_matches_pii_enum_and_demo_defaults_safe() -> None:
    catalog = load_yaml("project/privacy_policy.yaml")
    assert catalog["default_demo_mode"] is True
    assert set(catalog["pii_classes"]) == {state.value for state in PIIClass}
    assert "raw PersonContactPoint.value is not part of DemoContactPointRead" in catalog["demo_rules"]
