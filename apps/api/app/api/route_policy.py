from __future__ import annotations

from enum import StrEnum
from typing import Final


class RouteEffect(StrEnum):
    READ_ONLY = "READ_ONLY"
    COMPUTE_ONLY = "COMPUTE_ONLY"
    MUTATION_CAPABLE = "MUTATION_CAPABLE"


def _route(method: str, path: str) -> tuple[str, str]:
    return method.upper(), path


ROUTE_EFFECTS: Final[dict[tuple[str, str], RouteEffect]] = (
    {
        _route("GET", path): RouteEffect.READ_ONLY
        for path in (
            "/api/v1/health",
            "/api/v1/portfolio/projects",
            "/api/v1/projects",
            "/api/v1/projects/{project_id}",
            "/api/v1/projects/{project_id}/organizations",
            "/api/v1/projects/{project_id}/signals",
            "/api/v1/projects/{project_id}/evidence",
            "/api/v1/projects/{project_id}/quality",
            "/api/v1/projects/{project_id}/assessment",
            "/api/v1/organizations/{organization_id}",
            "/api/v1/organizations/{organization_id}/projects",
            "/api/v1/organizations/{organization_id}/contacts",
            "/api/v1/organizations/{organization_id}/intelligence",
            "/api/v1/organizations/{organization_id}/source-contacts",
            "/api/v1/projects/{project_id}/outcomes",
            "/api/v1/projects/{project_id}/contact-candidates",
            "/api/v1/projects/{project_id}/apollo-preview",
            "/api/v1/exceptions",
            "/api/v1/projects/{project_id}/actions",
            "/api/v1/projects/{project_id}/commercial-motions",
            "/api/v1/projects/{project_id}/crm-readiness",
            "/api/v1/projects/{project_id}/crm-preview",
            "/api/v1/pipeline/runs",
            "/api/v1/pipeline/runs/{run_id}",
            "/api/v1/metrics",
            "/api/v1/monday-brief",
            "/api/v1/readiness",
        )
    }
    | {
        _route("POST", path): RouteEffect.COMPUTE_ONLY
        for path in (
            "/api/v1/portfolio/triage",
            "/api/v1/projects/{project_id}/sensitivity",
            "/api/v1/analyst/query",
            "/api/v1/analyst/query/stream",
            "/api/v1/executive-brief/generate",
        )
    }
    | {
        _route("POST", path): RouteEffect.MUTATION_CAPABLE
        for path in (
            "/api/v1/ingest",
            "/api/v1/projects/{project_id}/outcomes",
            "/api/v1/contacts/{contact_id}/verification",
            "/api/v1/exceptions/{exception_id}/resolution",
            "/api/v1/projects/{project_id}/crm-sync",
            "/api/v1/projects/{project_id}/pipeline/refresh",
        )
    }
)


MUTATION_CAPABLE_ROUTES: Final[frozenset[tuple[str, str]]] = frozenset(
    key for key, effect in ROUTE_EFFECTS.items() if effect is RouteEffect.MUTATION_CAPABLE
)
