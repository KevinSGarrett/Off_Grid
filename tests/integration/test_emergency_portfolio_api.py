from __future__ import annotations

import re


def test_portfolio_reconciles_source_rows_without_fabricating_scores(wave14_full_state):
    client = wave14_full_state["client"]
    body = client.get("/api/v1/portfolio/projects").json()

    assert body["count"] == 165
    assert body["summary"]["source_project_rows"] == 167
    assert body["summary"]["canonical_projects"] == 165
    assert body["summary"]["projects_assessed"] == 1
    assert body["summary"]["projects_partially_assessable"] == 0
    assert body["summary"]["source_only_projects"] == 164
    assert body["summary"]["projects_with_insufficient_evidence"] == 0

    stafford = next(row for row in body["items"] if row["external_id"] == "1007341663")
    assert stafford["featured_case"] is True
    assert stafford["assessment_coverage"] == "FULL"
    assert float(stafford["commercial_fit_score"]) == 57.0
    assert stafford["commercial_band"] == "Promising candidate"
    assert stafford["operational_action"] == "VERIFY"
    assert stafford["data_confidence"] == "MEDIUM"

    source_only = next(row for row in body["items"] if row["id"] != stafford["id"])
    assert source_only["assessment_coverage"] == "SOURCE_ONLY"
    assert source_only["commercial_fit_score"] is None
    assert source_only["commercial_band"] is None
    assert source_only["operational_action"] is None


def test_generic_batch_triage_is_deterministic_unscored_and_write_free(wave14_full_state):
    client = wave14_full_state["client"]
    portfolio = client.get("/api/v1/portfolio/projects").json()["items"]
    stafford = next(row for row in portfolio if row["external_id"] == "1007341663")
    source_only = next(row for row in portfolio if row["id"] != stafford["id"])
    payload = {"project_ids": [stafford["id"], source_only["id"], stafford["id"]]}

    first = client.post("/api/v1/portfolio/triage", json=payload).json()
    second = client.post("/api/v1/portfolio/triage", json=payload).json()

    assert first == second
    assert first["total_records"] == 2
    assert first["full_eligible"] == 1
    assert first["source_only"] == 1
    assert first["assessed"] == 1
    assert first["external_writes_executed"] == 0
    assert len(first["ranked_assessments"]) == 1
    source_item = next(row for row in first["items"] if row["project_id"] == source_only["id"])
    assert source_item["commercial_fit_score"] is None
    assert source_item["commercial_band"] is None
    assert source_item["reason_codes"] == ["COMPANY_HISTORY_SOURCE_ONLY", "DETAILED_PROJECT_REPORT_REQUIRED"]


def test_generic_batch_triage_does_not_require_stafford(wave14_full_state):
    client = wave14_full_state["client"]
    portfolio = client.get("/api/v1/portfolio/projects").json()["items"]
    source_only = next(row for row in portfolio if row["external_id"] != "1007341663")

    body = client.post("/api/v1/portfolio/triage", json={"project_ids": [source_only["id"]]}).json()

    assert body["total_records"] == 1
    assert body["full_eligible"] == 0
    assert body["source_only"] == 1
    assert body["ranked_assessments"] == []
    assert body["external_writes_executed"] == 0


def test_ee_reed_intelligence_exposes_persisted_population_counts(wave14_full_state):
    client = wave14_full_state["client"]
    organization_id = wave14_full_state["ids"]["organization"]
    body = client.get(f"/api/v1/organizations/{organization_id}/intelligence").json()

    assert body["constructconnect_company_id"] == "1000647848"
    assert body["source_project_rows"] == 167
    assert body["unique_projects"] == 165
    assert body["source_section_counts"] == {
        "BIDDING": 0,
        "BIDDING_ROLE": 74,
        "PLANNING": 6,
        "POST_BID": 87,
    }
    assert body["source_contact_rows"] == 32
    assert body["canonical_source_contacts"] == 32
    assert body["generic_inbox_records"] == 5
    assert body["inactive_source_contacts"] == 1
    assert body["known_domain_count"] == 3
    assert body["report_date"].startswith("2026-07-08")
    assert body["source_company_last_update"] is not None
    assert body["source_company_last_update"] != body["report_date"]


def test_source_directory_is_demo_safe_and_distinct_from_stafford_candidates(
    wave14_full_state,
):
    client = wave14_full_state["client"]
    organization_id = wave14_full_state["ids"]["organization"]
    project_id = wave14_full_state["ids"]["project"]
    body = client.get(
        f"/api/v1/organizations/{organization_id}/source-contacts?comparison_project_id={project_id}"
    ).json()

    assert body["demo_mode"] is True
    assert body["source_row_count"] == 32
    assert body["count"] == 32
    assert body["funnel"]["canonical_source_identities"] == 32
    assert body["funnel"]["source_people_with_any_project_association"] == 11
    assert body["funnel"]["project_research_candidates"] == 6
    assert body["funnel"]["authority_verified"] == 0
    assert body["funnel"]["top_candidate"] == "Doug Meadows"
    assert body["funnel"]["sets_are_distinct"] is True
    assert sum(row["generic_inbox"] for row in body["items"]) == 5
    assert any(row["source_status"] == "INACTIVE" for row in body["items"])
    assert any(row["identity_quality"] == "REVIEW" for row in body["items"])
    assert all(row["rank_eligible"] is False for row in body["items"])
    rendered = str(body)
    assert not re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", rendered, re.IGNORECASE)
    assert "context/private_source_documents" not in rendered
    assert "file://" not in rendered


def test_project_candidates_expose_sanitized_evidence_origin(wave14_full_state):
    client = wave14_full_state["client"]
    project_id = wave14_full_state["ids"]["project"]

    body = client.get(f"/api/v1/projects/{project_id}/contact-candidates").json()

    assert body["count"] == 6
    assert all(candidate["evidence_origins"] for candidate in body["items"])
    assert all(
        set(candidate["evidence_origins"])
        <= {"COMPANY_WEBSITE", "PROJECT_SPECIFIC_PUBLIC_RESEARCH"}
        for candidate in body["items"]
    )


def test_apollo_search_and_enrichment_preview_execute_no_external_request(
    wave14_full_state,
):
    client = wave14_full_state["client"]
    project_id = wave14_full_state["ids"]["project"]

    body = client.get(f"/api/v1/projects/{project_id}/apollo-preview").json()

    assert body["eligible"] is True
    assert body["organization"] == "EE Reed Construction"
    assert body["search"]["mode"] == "PREVIEW"
    assert body["search"]["credit_consuming"] is False
    assert body["search"]["external_request_executed"] is False
    assert body["enrichment"]["display_name"] == "Doug Meadows"
    assert body["enrichment"]["request"]["credit_consuming"] is True
    assert body["enrichment"]["request"]["external_request_executed"] is False
    assert body["enrichment"]["before"]["rental_authority"] == "UNKNOWN"
    assert body["external_requests_executed"] == 0
    assert any(
        "cannot independently verify" in item
        for item in body["enrichment"]["constraints"]
    )


def test_integration_readiness_uses_configuration_state_not_connection_claims(
    wave14_full_state,
):
    body = wave14_full_state["client"].get("/api/v1/readiness").json()

    assert body["demo_mode"] is True
    assert body["integrations"]["constructconnect"]["status"] == "INGESTED_SOURCE"
    assert body["integrations"]["apollo"]["status"] == "PREVIEW"
    assert body["integrations"]["apollo"]["live_capable"] is True
    assert body["integrations"]["apollo"]["connection_checked"] is False
    assert body["integrations"]["pipedrive"]["status"] == "DRY_RUN"
    assert body["integrations"]["pipedrive"]["live_capable"] is False
    assert body["integrations"]["pipedrive"]["external_writes_enabled"] is False
