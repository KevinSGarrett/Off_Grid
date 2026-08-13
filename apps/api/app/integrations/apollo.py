from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from app.domain.errors import IntegrationUnavailableError
from app.domain.states import IntegrationMode
from app.core.settings import settings
from app.observability.logging import get_logger
from app.resilience import RetryPolicy, retry_call


@dataclass(frozen=True)
class ApolloRequestPreview:
    mode: IntegrationMode
    method: str
    endpoint: str
    params: dict[str, Any]
    body: dict[str, Any] | None
    credit_consuming: bool
    executed: bool
    note: str


logger = get_logger("apollo")


class ApolloAdapter:
    """Safe Apollo search/enrichment adapter.

    Search can be previewed without credentials. LIVE calls require both APOLLO_MODE=live and
    an explicit per-call `allow_live=True`; no contact-resolution workflow calls Apollo live automatically.
    """

    SEARCH_ENDPOINT = "https://api.apollo.io/api/v1/mixed_people/api_search"
    ENRICH_ENDPOINT = "https://api.apollo.io/api/v1/people/match"

    def __init__(
        self,
        mode: IntegrationMode | None = None,
        api_key: str | None = None,
        *,
        retry_policy: RetryPolicy | None = None,
    ):
        self.mode = mode or settings.apollo_mode
        self.api_key = api_key if api_key is not None else os.getenv("APOLLO_API_KEY")
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=3)

    def preview_search(
        self,
        *,
        titles: list[str],
        domains: list[str],
        person_locations: list[str] | None = None,
        per_page: int = 25,
    ) -> ApolloRequestPreview:
        params: dict[str, Any] = {
            "person_titles[]": titles,
            "include_similar_titles": True,
            "q_organization_domains_list[]": domains,
            "per_page": min(max(per_page, 1), 100),
            "page": 1,
        }
        if person_locations:
            params["person_locations[]"] = person_locations
        return ApolloRequestPreview(
            mode=self.mode,
            method="POST",
            endpoint=self.SEARCH_ENDPOINT,
            params=params,
            body=None,
            credit_consuming=False,
            executed=False,
            note="People Search is discovery-only; email/phone enrichment is a later selected-candidate step.",
        )

    def preview_enrichment(self, *, name: str, domain: str) -> ApolloRequestPreview:
        return ApolloRequestPreview(
            mode=self.mode,
            method="POST",
            endpoint=self.ENRICH_ENDPOINT,
            params={
                "name": name,
                "domain": domain,
                "reveal_personal_emails": False,
                "reveal_phone_number": False,
            },
            body=None,
            credit_consuming=True,
            executed=False,
            note="Preview only. Enrichment is intentionally limited to selected candidates and may consume Apollo credits.",
        )

    def search_people(self, preview: ApolloRequestPreview, *, allow_live: bool = False) -> dict[str, Any]:
        if self.mode is IntegrationMode.OFF:
            raise IntegrationUnavailableError("Apollo is disabled (APOLLO_MODE=off)")
        if self.mode in {IntegrationMode.PREVIEW, IntegrationMode.DRY_RUN}:
            return {"preview": True, "request": preview}
        if self.mode is not IntegrationMode.LIVE or not allow_live:
            raise IntegrationUnavailableError("Apollo live network action requires APOLLO_MODE=live and explicit allow_live=True")
        if not self.api_key:
            raise IntegrationUnavailableError("Apollo API key is not configured")
        def operation() -> dict[str, Any]:
            with httpx.Client(timeout=20) as client:
                response = client.request(
                    preview.method,
                    preview.endpoint,
                    params=preview.params,
                    headers={"x-api-key": self.api_key, "accept": "application/json"},
                )
                response.raise_for_status()
                return response.json()

        def retryable(exc: BaseException) -> bool:
            if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
                return True
            if isinstance(exc, httpx.HTTPStatusError):
                return exc.response.status_code == 429 or exc.response.status_code >= 500
            return False

        def on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            logger.warning(
                "apollo.request.retry",
                extra={
                    "safe_extra": {
                        "attempt": attempt,
                        "next_delay_seconds": delay,
                        "error_code": type(exc).__name__,
                        "endpoint": preview.endpoint,
                    }
                },
            )

        return retry_call(
            operation,
            policy=self.retry_policy,
            is_retryable=retryable,
            on_retry=on_retry,
        )
