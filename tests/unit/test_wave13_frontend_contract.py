from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/"apps/web/src/App.tsx").read_text();API=(ROOT/"apps/web/src/api.ts").read_text();CSS=(ROOT/"apps/web/src/styles.css").read_text()
def test_guided_ceo_review_covers_all_six_questions():
    for text in ["Is Stafford worth pursuing?","Who should we investigate?","What stands out in EE Reed?","Where does the pipeline break?","One number Monday morning?","What happens in the first two weeks?"]:assert text in APP
    assert APP.count('q:"Question ')==6
def test_frontend_consumes_api_instead_of_copying_business_rules():
    for path in ["/projects?limit=500","/assessment","/evidence","/quality","/organizations","/contact-candidates","/commercial-motions","/actions","/crm-preview","/crm-readiness","/sensitivity","/metrics","/monday-brief"]:assert path in API
    assert "80.00" not in APP and "69.25" not in APP and "qualification.yaml" not in APP and "crm-sync" not in API
def test_wave13_employer_experiences_are_present():
    for text in ["Command Center","Guided CEO Review","Stafford Intelligence","Evidence Inspector","EE Reed Account","Contact Resolution","Commercial Motion","Exception Queue","CRM Preview","Commercial Analyst","Monday Morning Brief","From raw data to commercial intelligence","First two weeks","Challenge the recommendation"]:assert text in APP
def test_frontend_has_no_raw_private_path_or_secret_surface():
    combined=APP+API
    for forbidden in ["context/private_source_documents","/mnt/data/","file://","OPENAI_API_KEY"]:assert forbidden not in combined
    assert "DEMO SAFE" in APP and "No raw PDFs or external writes" in APP
def test_responsive_mobile_navigation_is_implemented():
    assert "mobile" in APP and "@media(max-width:800px)" in CSS and "@media(max-width:520px)" in CSS
