from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "apps/web/src/App.tsx").read_text(encoding="utf-8")
COMPACT_APP = " ".join(APP.split())
API = (ROOT / "apps/web/src/api.ts").read_text(encoding="utf-8")
CSS = (ROOT / "apps/web/src/styles.css").read_text(encoding="utf-8")
TYPES = (ROOT / "apps/web/src/types.ts").read_text(encoding="utf-8")
METRICS = (ROOT / "apps/api/app/reporting/metrics.py").read_text(encoding="utf-8")


def test_guided_ceo_review_covers_all_six_questions():
    for text in [
        "Is Stafford worth pursuing?",
        "Who should we contact?",
        "What stands out in EE Reed?",
        "Where does the pipeline break?",
        "What matters Monday morning?",
        "What happens in the first two weeks?",
    ]:
        assert text in APP
    assert APP.count('q: "Question ')==6


def test_frontend_consumes_api_instead_of_copying_business_rules():
    for path in [
        "/projects?limit=500",
        "/assessment",
        "/evidence",
        "/quality",
        "/organizations",
        "/contact-candidates",
        "/commercial-motions",
        "/actions",
        "/crm-preview",
        "/crm-readiness",
        'client<SystemReadiness>("/readiness")',
        "/sensitivity",
        "/metrics",
        "/monday-brief",
    ]:
        assert path in API
    assert "80.00" not in APP and "69.25" not in APP and "qualification.yaml" not in APP and "crm-sync" not in API
    assert APP.count("d.actions.first_call_kit.questions.map") == 3
    assert "Who owns temporary lighting and portable power decisions?" not in APP
    assert "Can you confirm your current role and Stafford responsibilities?" not in APP


def test_employer_ui_uses_discrete_confidence_and_backend_workflow_semantics():
    for unsupported in ['`${n} percent`', "score(confidence)}%", "? 64 : 24", "index < (contractor"]:
        assert unsupported not in APP
    assert "Evidence quality / completeness" in APP
    assert "not a probability or Commercial Fit score" in COMPACT_APP
    assert "motion.dependency_map.map" in APP
    assert "motion.demand_display" in APP
    assert "Why contractor-side validation comes first" in APP
    assert "Product-fit signals" not in APP


def test_exception_and_metric_labels_do_not_conflate_database_concepts():
    for label in [
        "Open workflow exceptions",
        "Quality warnings requiring review",
        "Progression-blocking quality warnings",
        "Quality review items",
        "Projects assessed",
        "Investigation priority",
    ]:
        assert label in APP or label in TYPES or label in METRICS
    assert "metricLabel(monday.metric_definitions, key)" in APP
    assert "item.review_status" in APP
    assert "item.recommended_action" in APP


def test_utility_controls_and_combined_status_badges_are_truthful():
    assert 'placeholder="Search application views…"' in APP
    assert "Search projects, accounts, contacts…" not in APP
    assert 'aria-label="Notifications unavailable"' in APP
    assert 'title="No live notification service" disabled' in COMPACT_APP
    assert 'onClick={() => navigate("guided")}' in APP
    assert '<div className="account-button" aria-label="Demo account identity">' in APP
    assert 'value.map(pillText).join("")' in APP


def test_crm_preview_uses_the_backend_contract_and_type_critical_boundaries():
    for legacy in ["recommended_promotion", "idempotency_key", "request.action", "request.payload"]:
        assert legacy not in APP
    for current in [
        "permitted_promotion", "request.label", "request.body", "request.canonical_key",
        "request.method", "request.path", "request.dependencies", "request.status",
        "request.blocked_reason",
    ]:
        assert current in APP
    for contract in [
        "type Project =", "type Assessment =", "type QualityWarning =", "type Evidence =",
        "type ContactCandidate =", "type CommercialAction =", "type CommercialMotion =",
        "type CRMReadiness =", "type CRMRequest =", "type Metrics =", "type MondayBrief =",
        "type SystemReadiness =",
    ]:
        assert contract in TYPES
    assert "export type ApiRecord = Record<string, any>" not in TYPES
    assert "client<CRMPreview>" in API and "client<CRMReadiness>" in API
    assert "CRM Lead record ready" in APP
    assert "Lead-record readiness is not outreach authority or Deal readiness" in APP


def test_commercial_analyst_status_comes_from_backend_readiness():
    assert "OpenAI configured" not in APP
    assert "d.systemReadiness?.integrations?.openai" in APP
    for label in ["OpenAI enabled", "OpenAI disabled", "OpenAI unavailable"]:
        assert label in APP
    assert 'client<SystemReadiness>("/readiness")' in API


def test_optional_dashboard_dependencies_degrade_in_place_and_can_retry():
    for key in ["analyst_readiness", "metrics", "crm_preview", "monday_brief"]:
        assert key in API
        assert key in APP
    assert "CORE_BOOT_ENDPOINTS" in API
    assert "OPTIONAL_BOOT_ENDPOINTS" in API
    assert "retryOptionalDependency" in API
    assert "DegradedPanel" in APP
    assert "Core intelligence remains available" in API
    assert "response.text()" not in API
    assert "x-request-id" in API


def test_wave13_employer_experiences_are_present():
    for text in [
        "Command Center",
        "Guided CEO Review",
        "Project Intelligence",
        "Evidence Inspector",
        "Account Intelligence",
        "Contact Resolution",
        "Product Fit",
        "Commercial Motion",
        "Exception Queue",
        "CRM Preview",
        "Commercial Analyst",
        "Monday Morning Brief",
        "First 14 Days",
        "Counterfactual sensitivity",
    ]:
        assert text in APP


def test_frontend_has_no_raw_private_path_or_secret_surface():
    combined = APP + API
    for forbidden in [
        "context/private_source_documents",
        "/mnt/data/",
        "file://",
        "OPENAI_API_KEY",
    ]:
        assert forbidden not in combined
    assert "DEMO SAFE" in APP and "No raw PDFs or external writes" in APP


def test_responsive_mobile_navigation_is_implemented():
    assert "mobile-menu" in APP
    assert 'aria-label="Primary navigation"' in APP
    assert ".sidebar.open" in CSS
    assert ".sidebar { display: none" not in CSS
    assert 'aria-label="Guided CEO Review"' in APP
    assert "aria-label={item.label}" in APP
    assert "@media (max-width: 820px)" in CSS
    assert "@media (max-width: 600px)" in CSS


def test_desktop_navigation_is_viewport_fixed_and_scroll_contained():
    assert ".sidebar { position: fixed" in CSS
    assert "overscroll-behavior: contain" in CSS
    assert "scrollbar-gutter: stable" in CSS
    assert ".workspace { min-width: 0; grid-column: 2; }" in CSS
    assert "body { margin: 0; min-width: 320px; min-height: 100vh; overflow-x: clip; overscroll-behavior: none; }" in CSS


def test_product_fit_keeps_relevance_index_separate_from_applicability():
    assert "characteristic_relevance_score" in APP
    assert "Characteristic relevance" in APP
    assert "Deterministic project-characteristic score" in APP
    assert "validated" in APP and "forecast, or probability" in APP
    assert "applicability_status" in APP
    assert ".applicability-row > .pill { grid-column: 2" in CSS


def test_diagnostics_are_independently_scaled_not_equal_funnel_blocks():
    assert "diagnosticEntries" in APP
    assert "value / maxDiagnosticValue" in APP
    assert "Independently scaled inventory diagnostics" in APP
    assert ".diagnostic-track i" in CSS
    assert ".funnel-bars div" not in CSS


def test_project_data_opens_on_the_broad_company_history_not_the_single_record():
    assert 'useState<"detailed" | "history">("history")' in APP
    assert "EE Reed project history ({summary.company_history_projects} source records)" in APP
    assert "Detailed assessment queue ({summary.detailed_project_records} eligible)" in APP


def test_reference_aligned_views_are_url_addressable_and_fluid():
    for key in [
        "guided",
        "command",
        "project",
        "account",
        "contacts",
        "evidence",
        "product",
        "exceptions",
        "crm",
        "commercial",
        "analyst",
        "monday",
        "roadmap",
    ]:
        assert f'data-view="{key}"' in APP
    assert "window.location.hash" in APP
    assert "width:min(1180px,100%)" not in CSS.replace(" ", "")


def test_emergency_portfolio_and_source_views_preserve_coverage_boundaries():
    for text in [
        "Project Data",
        "Account / Source Data",
        "Generic batch triage:",
        "No qualification score inferred",
        "Directory rows are not Stafford candidate rankings",
        "Full commercial assessment unavailable",
        "Stafford evidence, contacts, product applicability, CRM readiness, and analyst conclusions are never reused",
    ]:
        assert text in APP
    for path in [
        "/portfolio/projects",
        "/intelligence",
        "/source-contacts",
        "/apollo-preview",
    ]:
        assert path in API
    assert 'data-view="portfolio"' in APP
    assert 'data-view="source"' in APP
    assert "selectedIsFeatured" in APP
    assert "UnavailableProjectLayer" in APP


def test_commercial_preview_actions_are_explicit_and_fail_closed():
    for text in [
        "Preview Apollo Search",
        "Preview Enrichment",
        "Preview Pipedrive Sync",
        "External request executed: NO",
        "EXTERNAL WRITES:",
        "Create Deal",
        "The source-reported project value is excluded from Deal value",
        "Configuration state; not a live connection claim",
    ]:
        assert text.lower() in APP.lower()
    assert "disabled title=\"Blocked: rental authority" in APP
    assert "d.apollo.enrichment?.constraints" in APP
    assert "d.crm.external_writes_executed" in APP
