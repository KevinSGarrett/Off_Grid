from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.states import EvidenceClassification
from app.scoring.config import LoadedConfig, ScoringConfigurationError, load_yaml_config


@dataclass(frozen=True)
class ProductFact:
    statement: str
    classification: EvidenceClassification
    source: str


@dataclass(frozen=True)
class ProductDefinition:
    code: str
    name: str
    approved_facts: tuple[ProductFact, ...]
    unknown_specifications: tuple[str, ...]
    fit_rules: tuple[dict, ...]
    validation_gate: dict
    required_evidence: tuple[dict, ...]


@dataclass(frozen=True)
class ProductRegistry:
    version: str
    source_basis: str
    forbidden_inventions: tuple[str, ...]
    products: tuple[ProductDefinition, ...]
    loaded: LoadedConfig

    def by_code(self, code: str) -> ProductDefinition:
        for product in self.products:
            if product.code == code:
                return product
        raise KeyError(code)


def load_product_registry(path: str | Path = "config/products.yaml") -> ProductRegistry:
    loaded = load_yaml_config(path)
    data = loaded.data
    registry = data.get("registry")
    rows = data.get("products")
    if not isinstance(registry, dict) or not isinstance(rows, list):
        raise ScoringConfigurationError("products config requires registry and products")
    products: list[ProductDefinition] = []
    seen: set[str] = set()
    for row in rows:
        code = str(row.get("code", "")).strip()
        if not code or code in seen:
            raise ScoringConfigurationError(f"product code missing/duplicated: {code}")
        seen.add(code)
        facts: list[ProductFact] = []
        for fact in row.get("approved_facts", []):
            classification = EvidenceClassification(fact.get("classification", "EXPLICIT"))
            if classification not in {EvidenceClassification.EXPLICIT, EvidenceClassification.VERIFIED}:
                raise ScoringConfigurationError(
                    f"approved product fact for {code} must be EXPLICIT or VERIFIED"
                )
            facts.append(
                ProductFact(
                    statement=str(fact["statement"]),
                    classification=classification,
                    source=str(fact["source"]),
                )
            )
        if not facts:
            raise ScoringConfigurationError(f"product {code} requires at least one approved fact")
        products.append(
            ProductDefinition(
                code=code,
                name=str(row.get("name") or code),
                approved_facts=tuple(facts),
                unknown_specifications=tuple(str(x) for x in row.get("unknown_specifications", [])),
                fit_rules=tuple(dict(x) for x in row.get("fit_rules", [])),
                validation_gate=dict(row.get("validation_gate") or {}),
                required_evidence=tuple(dict(x) for x in row.get("required_evidence", [])),
            )
        )
    if seen != {"KVT", "KV6", "KVP"}:
        raise ScoringConfigurationError(f"registry must contain exactly KVT/KV6/KVP, got {sorted(seen)}")
    return ProductRegistry(
        version=str(registry["version"]),
        source_basis=str(registry.get("source_basis", "")),
        forbidden_inventions=tuple(str(x) for x in registry.get("forbidden_inventions", [])),
        products=tuple(products),
        loaded=loaded,
    )
