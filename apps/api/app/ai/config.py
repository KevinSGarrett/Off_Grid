from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from app.core.settings import settings

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG_PATH = ROOT / "config/openai.yaml"


@dataclass(frozen=True, slots=True)
class ModelRoute:
    name: str
    model_id: str
    reasoning_effort: str
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    role: str


@dataclass(frozen=True, slots=True)
class TaskConfig:
    name: str
    model_route: str
    prompt_name: str
    prompt_version: str
    output_schema: str


@dataclass(frozen=True, slots=True)
class OpenAIIntelligenceConfig:
    name: str
    version: str
    verified_at: str
    official_sources: dict[str, str]
    enabled: bool
    research_enabled: bool
    raw_documents: bool
    store_responses: bool
    max_retries: int
    timeout_seconds: int
    daily_budget_usd: Decimal
    max_output_tokens: int
    max_tool_rounds: int
    model_routes: dict[str, ModelRoute]
    tasks: dict[str, TaskConfig]
    safety: dict[str, Any]

    def route_for_task(self, task: str) -> tuple[TaskConfig, ModelRoute]:
        task_cfg = self.tasks[task]
        return task_cfg, self.model_routes[task_cfg.model_route]


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def load_openai_config(path: Path | None = None) -> OpenAIIntelligenceConfig:
    raw = yaml.safe_load((path or DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))["openai"]
    defaults = raw["defaults"]
    routes: dict[str, ModelRoute] = {}
    for name, row in raw["models"].items():
        configured_id = {
            "fast": settings.openai_model_fast,
            "reasoning": settings.openai_model_reasoning,
            "research": settings.openai_model_research,
        }.get(name, str(row["id"]))
        routes[name] = ModelRoute(
            name=name,
            model_id=configured_id or str(row["id"]),
            reasoning_effort=str(row["reasoning_effort"]),
            input_usd_per_million=_decimal(row["input_usd_per_million"]),
            cached_input_usd_per_million=_decimal(row["cached_input_usd_per_million"]),
            output_usd_per_million=_decimal(row["output_usd_per_million"]),
            role=str(row["role"]),
        )
    tasks = {
        name: TaskConfig(
            name=name,
            model_route=str(row["model_route"]),
            prompt_name=str(row["prompt_name"]),
            prompt_version=str(row["prompt_version"]),
            output_schema=str(row["output_schema"]),
        )
        for name, row in raw["tasks"].items()
    }
    return OpenAIIntelligenceConfig(
        name=str(raw["name"]),
        version=str(raw["version"]),
        verified_at=str(raw["verified_at"]),
        official_sources=dict(raw["official_sources"]),
        enabled=settings.openai_enabled if path is None else bool(defaults["enabled"]),
        research_enabled=(
            settings.openai_research_enabled if path is None else bool(defaults["research_enabled"])
        ),
        raw_documents=(settings.openai_raw_documents if path is None else bool(defaults["raw_documents"])),
        store_responses=bool(defaults["store_responses"]),
        max_retries=settings.openai_max_retries if path is None else int(defaults["max_retries"]),
        timeout_seconds=(
            settings.openai_timeout_seconds if path is None else int(defaults["timeout_seconds"])
        ),
        daily_budget_usd=(
            settings.openai_daily_budget if path is None else _decimal(defaults["daily_budget_usd"])
        ),
        max_output_tokens=int(defaults["max_output_tokens"]),
        max_tool_rounds=int(defaults["max_tool_rounds"]),
        model_routes=routes,
        tasks=tasks,
        safety=dict(raw["safety"]),
    )
