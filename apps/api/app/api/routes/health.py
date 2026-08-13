from __future__ import annotations

import os

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import __version__
from app.api.dependencies import get_runtime_policy, get_session
from app.core.settings import settings
from app.observability.context import current_context
from app.observability.logging import OBSERVABILITY_VERSION

router = APIRouter(tags=["platform"])


@router.get("/health")
def health(policy=Depends(get_runtime_policy)) -> dict[str, object]:
    return {
        "status": "ok",
        "service": "offgrid-commercial-intelligence-api",
        "version": __version__,
        "demo_mode": policy.demo_mode,
        "api_version": "backend-api-1.0",
        "observability_version": OBSERVABILITY_VERSION,
        "request_id": current_context()["request_id"],
    }


@router.get("/readiness")
def readiness(
    session: Session = Depends(get_session),
    policy=Depends(get_runtime_policy),
) -> dict[str, object]:
    database_ready = True
    database_error_code = None
    try:
        session.execute(sa.text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - deployment failure probe path
        database_ready = False
        database_error_code = type(exc).__name__

    # Readiness does not ping paid/external providers. It reports configured local policy only so
    # health checks cannot trigger cost, leak credentials, or turn optional enrichment into a hard
    # dependency of the deterministic pipeline.
    integrations = {
        "openai": {
            "enabled": settings.openai_enabled,
            "credentials_present": bool(settings.openai_api_key),
            "status": (
                "ENABLED"
                if settings.openai_enabled and settings.openai_api_key
                else "CREDENTIALS_MISSING"
                if settings.openai_enabled
                else "OFF"
            ),
            "implemented": True,
            "connection_checked": False,
            "hard_dependency": False,
        },
        "constructconnect": {
            "status": "INGESTED_SOURCE",
            "mode": "supplied_reports",
            "implemented": True,
            "hard_dependency": False,
        },
        "apollo": {
            "mode": settings.apollo_mode.value,
            "status": "PREVIEW" if policy.demo_mode else settings.apollo_mode.value.upper(),
            "implemented": True,
            "live_capable": True,
            "credentials_present": bool(os.getenv("APOLLO_API_KEY")),
            "search_available": True,
            "enrichment_gated": True,
            "connection_checked": False,
            "hard_dependency": False,
        },
        "pipedrive": {
            "mode": settings.pipedrive_mode.value,
            "status": "DRY_RUN" if policy.demo_mode else settings.pipedrive_mode.value.upper(),
            "implemented": True,
            "live_capable": False,
            "credentials_present": bool(
                os.getenv("PIPEDRIVE_API_TOKEN") or os.getenv("PIPEDRIVE_OAUTH_TOKEN")
            ),
            "external_writes_enabled": False,
            "connection_checked": False,
            "hard_dependency": False,
        },
        "trello": {
            "mode": settings.trello_mode.value,
            "status": "CONTRACT" if policy.demo_mode else settings.trello_mode.value.upper(),
            "hard_dependency": False,
        },
        "google": {
            "mode": settings.google_mode.value,
            "status": "CONTRACT" if policy.demo_mode else settings.google_mode.value.upper(),
            "hard_dependency": False,
        },
    }
    return {
        "status": "ready" if database_ready else "degraded",
        "architecture_version": "ARCH-0.3.0",
        "api_version": "backend-api-1.0",
        "pipeline_version": "pipeline-orchestration-1.0",
        "observability_version": OBSERVABILITY_VERSION,
        "request_id": current_context()["request_id"],
        "database": {
            "ready": database_ready,
            "error_code": database_error_code,
        },
        # Compatibility field retained for existing dashboards/tests.
        "database_ready": database_ready,
        "demo_mode": policy.demo_mode,
        "openai_enabled": settings.openai_enabled,
        "pipedrive_mode": settings.pipedrive_mode.value,
        "integrations": integrations,
        "external_writes_allowed": False if policy.demo_mode else "gated_by_owner_integration",
    }
