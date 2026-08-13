from __future__ import annotations

import os
from dataclasses import dataclass, field
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
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    demo_mode: bool = field(default_factory=lambda: _bool("DEMO_MODE", True))
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./data/private/offgrid.db")
    )
    auto_create_schema: bool = field(default_factory=lambda: _bool("AUTO_CREATE_SCHEMA", False))
    serve_web: bool = field(default_factory=lambda: _bool("SERVE_WEB", False))
    web_static_dir: str = field(
        default_factory=lambda: os.getenv("WEB_STATIC_DIR", "apps/web/dist")
    )
    require_access_control: bool = field(
        default_factory=lambda: _bool("REQUIRE_ACCESS_CONTROL", False)
    )
    app_access_password: str | None = field(
        default_factory=lambda: os.getenv("APP_ACCESS_PASSWORD") or None
    )

    # OpenAI is an optional server-side intelligence layer. The deterministic core must work
    # with this disabled and without an API key.
    openai_enabled: bool = field(default_factory=lambda: _bool("OPENAI_ENABLED", False))
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY") or None)
    openai_model_fast: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL_FAST", "gpt-5.6-luna")
    )
    openai_model_reasoning: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL_REASONING", "gpt-5.6-sol")
    )
    openai_model_research: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL_RESEARCH", "gpt-5.6-terra")
    )
    openai_research_enabled: bool = field(
        default_factory=lambda: _bool("OPENAI_RESEARCH_ENABLED", False)
    )
    openai_daily_budget: Decimal = field(
        default_factory=lambda: _decimal("OPENAI_DAILY_BUDGET", Decimal("2.00"))
    )
    openai_max_retries: int = field(default_factory=lambda: _int("OPENAI_MAX_RETRIES", 2))
    openai_timeout_seconds: int = field(default_factory=lambda: _int("OPENAI_TIMEOUT_SECONDS", 180))
    openai_raw_documents: bool = field(default_factory=lambda: _bool("OPENAI_RAW_DOCUMENTS", False))

    apollo_mode: IntegrationMode = field(
        default_factory=lambda: _mode("APOLLO_MODE", IntegrationMode.OFF)
    )
    pipedrive_mode: IntegrationMode = field(
        default_factory=lambda: _mode("PIPEDRIVE_MODE", IntegrationMode.DRY_RUN)
    )
    trello_mode: IntegrationMode = field(
        default_factory=lambda: _mode("TRELLO_MODE", IntegrationMode.OFF)
    )
    google_mode: IntegrationMode = field(
        default_factory=lambda: _mode("GOOGLE_INTEGRATION_MODE", IntegrationMode.OFF)
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())


settings = Settings()
