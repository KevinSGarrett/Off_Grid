from __future__ import annotations

import pytest

from app.domain.errors import IntegrationUnavailableError
from app.domain.states import IntegrationMode
from app.integrations.apollo import ApolloAdapter


def test_apollo_preview_search_is_discovery_only_and_uses_current_endpoint_contract() -> None:
    adapter = ApolloAdapter(mode=IntegrationMode.PREVIEW)
    request = adapter.preview_search(
        titles=["Project Executive", "Superintendent"],
        domains=["eereedeast.com"],
        person_locations=["Virginia"],
    )
    assert request.endpoint == "https://api.apollo.io/api/v1/mixed_people/api_search"
    assert request.credit_consuming is False
    assert request.executed is False
    assert request.params["q_organization_domains_list[]"] == ["eereedeast.com"]
    assert "person_titles[]" in request.params
    assert adapter.search_people(request)["preview"] is True


def test_apollo_enrichment_is_selected_candidate_step_and_preview_never_executes() -> None:
    adapter = ApolloAdapter(mode=IntegrationMode.PREVIEW)
    request = adapter.preview_enrichment(name="Doug Meadows", domain="eereedeast.com")
    assert request.endpoint == "https://api.apollo.io/api/v1/people/match"
    assert request.credit_consuming is True
    assert request.params["reveal_personal_emails"] is False
    assert request.params["reveal_phone_number"] is False
    assert request.executed is False


def test_apollo_live_requires_explicit_runtime_opt_in_and_credentials() -> None:
    adapter = ApolloAdapter(mode=IntegrationMode.LIVE, api_key=None)
    request = adapter.preview_search(titles=["Project Executive"], domains=["eereedeast.com"])
    with pytest.raises(IntegrationUnavailableError, match="explicit allow_live"):
        adapter.search_people(request, allow_live=False)
    with pytest.raises(IntegrationUnavailableError, match="API key"):
        adapter.search_people(request, allow_live=True)
