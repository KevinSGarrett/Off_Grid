from fastapi.testclient import TestClient

from app.main import app


def test_health_contract() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "offgrid-commercial-intelligence-api"
    assert body["version"] == "0.17.0"


def test_readiness_exposes_safe_architecture_state() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["architecture_version"] == "ARCH-0.3.0"
    assert body["pipedrive_mode"] in {"off", "preview", "dry_run", "live"}
