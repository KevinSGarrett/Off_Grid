from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.scoring.config import LoadedConfig, load_yaml_config


class CRMConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class CRMIntegrationConfig:
    loaded: LoadedConfig
    crm: dict[str, Any]
    reporting: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.crm["version"])

    @property
    def reporting_version(self) -> str:
        return str(self.reporting["version"])


def load_crm_integration_config(path: str | Path = "config/integrations.yaml") -> CRMIntegrationConfig:
    loaded = load_yaml_config(path)
    crm = loaded.data.get("crm")
    reporting = loaded.data.get("reporting")
    if not isinstance(crm, dict) or not crm.get("version"):
        raise CRMConfigurationError("integrations config requires crm.version")
    if not isinstance(reporting, dict) or not reporting.get("version"):
        raise CRMConfigurationError("integrations config requires reporting.version")
    thresholds = crm.get("readiness", {})
    min_confidence = thresholds.get("minimum_data_confidence_for_lead")
    if not isinstance(min_confidence, (int, float)) or not 0 <= min_confidence <= 100:
        raise CRMConfigurationError("minimum_data_confidence_for_lead must be 0..100")
    endpoints = crm.get("pipedrive", {}).get("endpoints", {})
    required = {"organization_create", "person_create", "lead_create", "deal_create"}
    if not required.issubset(endpoints):
        raise CRMConfigurationError("Pipedrive endpoint contract is incomplete")
    if not isinstance(reporting.get("sheets", {}).get("columns"), list):
        raise CRMConfigurationError("reporting.sheets.columns must be a list")
    if not isinstance(reporting.get("forms", {}).get("questions"), list):
        raise CRMConfigurationError("reporting.forms.questions must be a list")
    return CRMIntegrationConfig(loaded=loaded, crm=crm, reporting=reporting)
