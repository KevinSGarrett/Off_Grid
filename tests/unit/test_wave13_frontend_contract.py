from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "apps/web/src/App.tsx").read_text(encoding="utf-8")
API = (ROOT / "apps/web/src/api.ts").read_text(encoding="utf-8")
CSS = (ROOT / "apps/web/src/styles.css").read_text(encoding="utf-8")


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
        'get<any>("/readiness")',
        "/sensitivity",
        "/metrics",
        "/monday-brief",
    ]:
        assert path in API
    assert "80.00" not in APP and "69.25" not in APP and "qualification.yaml" not in APP and "crm-sync" not in API
    assert APP.count("d.actions.first_call_kit.questions.map") == 3
    assert "Who owns temporary lighting and portable power decisions?" not in APP
    assert "Can you confirm your current role and Stafford responsibilities?" not in APP


def test_commercial_analyst_status_comes_from_backend_readiness():
    assert "OpenAI configured" not in APP
    assert "d.systemReadiness?.integrations?.openai" in APP
    for label in ["OpenAI enabled", "OpenAI disabled", "OpenAI unavailable"]:
        assert label in APP
    assert 'get<any>("/readiness")' in API


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
    assert "@media (max-width: 820px)" in CSS
    assert "@media (max-width: 600px)" in CSS


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
