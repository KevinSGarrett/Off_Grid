from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]


class ScoringConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedConfig:
    path: Path
    data: dict[str, Any]
    text: str
    sha256: str


def load_yaml_config(path: str | Path) -> LoadedConfig:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = REPO_ROOT / resolved
    text = resolved.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ScoringConfigurationError(f"Configuration must be a mapping: {resolved}")
    return LoadedConfig(path=resolved, data=data, text=text, sha256=sha256(text.encode("utf-8")).hexdigest())


def load_qualification_config(path: str | Path = "config/qualification.yaml") -> LoadedConfig:
    loaded = load_yaml_config(path)
    data = loaded.data
    model = data.get("model")
    factors = data.get("factors")
    if not isinstance(model, dict) or not isinstance(factors, list) or not factors:
        raise ScoringConfigurationError("qualification config requires model and non-empty factors")
    thresholds = model.get("thresholds", {})
    pursue = thresholds.get("pursue")
    review = thresholds.get("review")
    if not isinstance(pursue, (int, float)) or not isinstance(review, (int, float)) or pursue <= review:
        raise ScoringConfigurationError("qualification thresholds require pursue > review")

    factor_keys: set[str] = set()
    rule_keys: set[str] = set()
    max_total = 0.0
    for factor in factors:
        if not isinstance(factor, dict):
            raise ScoringConfigurationError("each factor must be a mapping")
        key = factor.get("key")
        if not key or key in factor_keys:
            raise ScoringConfigurationError(f"factor key missing/duplicated: {key}")
        factor_keys.add(key)
        max_points = float(factor.get("max_points", 0))
        if max_points <= 0:
            raise ScoringConfigurationError(f"factor {key} max_points must be positive")
        max_total += max_points
        points_sum = 0.0
        for rule in factor.get("rules", []):
            rkey = rule.get("key")
            if not rkey or rkey in rule_keys:
                raise ScoringConfigurationError(f"rule key missing/duplicated: {rkey}")
            rule_keys.add(rkey)
            points = float(rule.get("points", 0))
            if points < 0:
                raise ScoringConfigurationError(f"rule {rkey} cannot award negative points")
            points_sum += points
        if points_sum > max_points + 1e-9:
            raise ScoringConfigurationError(f"factor {key} rules exceed max_points")
    if abs(max_total - 100.0) > 1e-9:
        raise ScoringConfigurationError(f"factor max_points must total 100, got {max_total}")
    return loaded


def load_confidence_config(path: str | Path = "config/trust_confidence.yaml") -> LoadedConfig:
    loaded = load_yaml_config(path)
    data = loaded.data
    model = data.get("model", {})
    if not model.get("version"):
        raise ScoringConfigurationError("confidence model version is required")
    weights = 0.0
    for section in ("observation_components", "relationship_components", "completeness_components"):
        for item in data.get(section, []):
            weights += float(item.get("weight", 0))
    if abs(weights - 100.0) > 1e-9:
        raise ScoringConfigurationError(f"confidence component weights must total 100, got {weights}")
    return loaded
