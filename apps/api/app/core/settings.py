from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.domain.states import IntegrationMode


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _mode(name: str, default: IntegrationMode) -> IntegrationMode:
    raw = os.getenv(name, default.value).strip().lower()
    return IntegrationMode(raw)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _decimal(name: str, default: Decimal) -> Decimal:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal value") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    demo_mode: bool = _bool("DEMO_MODE", True)
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/private/offgrid.db")
    auto_create_schema: bool = _bool("AUTO_CREATE_SCHEMA", False)
    serve_web: bool = _bool("SERVE_WEB", False)
    web_static_dir: str = os.getenv("WEB_STATIC_DIR", "apps/web/dist")
    require_access_control: bool = _bool("REQUIRE_ACCESS_CONTROL", False)
    app_access_password: str | None = os.getenv("APP_ACCESS_PASSWORD") or None

    # OpenAI is an optional server-side intelligence layer. The deterministic core must work
    # with this disabled and without an API key.
    openai_enabled: bool = _bool("OPENAI_ENABLED", False)
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    openai_model_fast: str = os.getenv("OPENAI_MODEL_FAST", "gpt-5.6-luna")
    openai_model_reasoning: str = os.getenv("OPENAI_MODEL_REASONING", "gpt-5.6-terra")
    openai_model_research: str = os.getenv("OPENAI_MODEL_RESEARCH", "gpt-5.6-terra")
    openai_research_enabled: bool = _bool("OPENAI_RESEARCH_ENABLED", False)
    openai_daily_budget: Decimal = _decimal("OPENAI_DAILY_BUDGET", Decimal("2.00"))
    openai_max_retries: int = _int("OPENAI_MAX_RETRIES", 2)
    openai_timeout_seconds: int = _int("OPENAI_TIMEOUT_SECONDS", 45)
    openai_raw_documents: bool = _bool("OPENAI_RAW_DOCUMENTS", False)

    apollo_mode: IntegrationMode = _mode("APOLLO_MODE", IntegrationMode.OFF)
    pipedrive_mode: IntegrationMode = _mode("PIPEDRIVE_MODE", IntegrationMode.DRY_RUN)
    trello_mode: IntegrationMode = _mode("TRELLO_MODE", IntegrationMode.OFF)
    google_mode: IntegrationMode = _mode("GOOGLE_INTEGRATION_MODE", IntegrationMode.OFF)
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
