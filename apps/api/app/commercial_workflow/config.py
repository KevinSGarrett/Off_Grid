from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.scoring.config import LoadedConfig, load_yaml_config


class CommercialWorkflowConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class CommercialWorkflowConfig:
    loaded: LoadedConfig
    workflow: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.workflow["version"])


def load_commercial_workflow_config(
    path: str | Path = "config/commercial_workflow.yaml",
) -> CommercialWorkflowConfig:
    loaded = load_yaml_config(path)
    workflow = loaded.data.get("workflow")
    if not isinstance(workflow, dict):
        raise CommercialWorkflowConfigurationError("commercial workflow config requires workflow mapping")
    if not workflow.get("version"):
        raise CommercialWorkflowConfigurationError("workflow.version is required")
    actions = workflow.get("actions")
    if not isinstance(actions, list) or not actions:
        raise CommercialWorkflowConfigurationError("workflow.actions must be non-empty")
    keys = {str(row.get("key")) for row in actions if isinstance(row, dict)}
    if len(keys) != len(actions) or "None" in keys:
        raise CommercialWorkflowConfigurationError("workflow action keys must be present and unique")
    priorities: dict[str, int] = {}
    for row in actions:
        key = str(row.get("key"))
        try:
            priority = int(row["priority"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CommercialWorkflowConfigurationError(
                f"positive integer priority is required for action {key!r}"
            ) from exc
        if priority <= 0 or priority in priorities.values():
            raise CommercialWorkflowConfigurationError(
                f"workflow action priorities must be positive and unique; got {priority} for {key!r}"
            )
        priorities[key] = priority
        dependency = row.get("dependency")
        if dependency is not None and str(dependency) not in keys:
            raise CommercialWorkflowConfigurationError(
                f"unknown action dependency {dependency!r} for {row.get('key')!r}"
            )
        if str(row.get("motion")) not in {"CONTRACTOR", "RENTAL_HOUSE"}:
            raise CommercialWorkflowConfigurationError(f"invalid motion for action {row.get('key')}")
    for row in actions:
        dependency = row.get("dependency")
        if dependency is not None and priorities[str(dependency)] >= priorities[str(row["key"])]:
            raise CommercialWorkflowConfigurationError(
                f"dependency {dependency!r} must precede action {row['key']!r} by priority"
            )
    kit = workflow.get("first_call_kit", {})
    if not isinstance(kit.get("questions"), list) or len(kit["questions"]) < 6:
        raise CommercialWorkflowConfigurationError("first_call_kit requires at least six questions")
    return CommercialWorkflowConfig(loaded=loaded, workflow=workflow)
