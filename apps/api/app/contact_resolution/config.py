from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.scoring.config import LoadedConfig, load_yaml_config


class ContactResolutionConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ContactResolutionConfigs:
    contact: LoadedConfig
    personas: LoadedConfig
    precedence: LoadedConfig


def load_contact_resolution_configs(
    contact_path: str | Path = "config/contact_resolution.yaml",
    persona_path: str | Path = "config/personas.yaml",
    precedence_path: str | Path = "config/source_precedence.yaml",
) -> ContactResolutionConfigs:
    contact = load_yaml_config(contact_path)
    personas = load_yaml_config(persona_path)
    precedence = load_yaml_config(precedence_path)

    weights = contact.data.get("score_weights", {})
    if not isinstance(weights, dict) or sum(float(v) for v in weights.values()) != 100:
        raise ContactResolutionConfigurationError("contact score weights must total 100")
    if not contact.data.get("model", {}).get("version"):
        raise ContactResolutionConfigurationError("contact resolution model version is required")
    persona_rows = personas.data.get("personas")
    if not isinstance(persona_rows, list) or not persona_rows:
        raise ContactResolutionConfigurationError("personas config requires non-empty personas")
    keys = [row.get("key") for row in persona_rows]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ContactResolutionConfigurationError("persona keys must be present and unique")
    if not precedence.data.get("policy", {}).get("version"):
        raise ContactResolutionConfigurationError("source precedence version is required")
    required_attributes = {"employment", "project_association", "role_relevance", "rental_authority"}
    if not required_attributes.issubset(precedence.data.get("attributes", {})):
        raise ContactResolutionConfigurationError("source precedence missing contact attributes")
    return ContactResolutionConfigs(contact=contact, personas=personas, precedence=precedence)
