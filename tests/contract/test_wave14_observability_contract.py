from __future__ import annotations

import io
import json

from app.observability.context import bind_pipeline_run, bind_request
from app.observability.logging import configure_structured_logging, sanitize_for_log


def test_structured_log_is_json_correlated_and_redacted() -> None:
    stream = io.StringIO()
    logger = configure_structured_logging(stream=stream)
    with bind_request("req-contract-14"), bind_pipeline_run("run-contract-14"):
        logger.info(
            "contract.event",
            extra={
                "safe_extra": {
                    "email": "named.person@example.com",
                    "phone": "(281) 933-4000",
                    "source": "/mnt/data/private/report.pdf",
                    "api_key": "super-secret-value",
                }
            },
        )
    row = json.loads(stream.getvalue())
    assert row["event"] == "contract.event"
    assert row["request_id"] == "req-contract-14"
    assert row["pipeline_run_id"] == "run-contract-14"
    assert row["fields"]["api_key"] == "[REDACTED]"
    rendered = json.dumps(row)
    assert "named.person@example.com" not in rendered
    assert "(281) 933-4000" not in rendered
    assert "/mnt/data/private/report.pdf" not in rendered
    assert "super-secret-value" not in rendered


def test_sanitizer_masks_nested_secret_and_contact_values() -> None:
    value = sanitize_for_log(
        {
            "authorization": "Bearer 123",
            "nested": {"message": "Email user@company.com or call 281-933-4000"},
        }
    )
    assert value["authorization"] == "[REDACTED]"
    assert "user@company.com" not in value["nested"]["message"]
    assert "281-933-4000" not in value["nested"]["message"]


def test_health_and_readiness_are_correlated_and_do_not_ping_optional_providers(wave14_full_state) -> None:
    client = wave14_full_state["client"]
    request_id = "wave14-health-probe"
    health = client.get("/api/v1/health", headers={"X-Request-ID": request_id})
    assert health.status_code == 200
    assert health.headers["x-request-id"] == request_id
    assert health.json()["request_id"] == request_id
    assert health.json()["observability_version"] == "observability-1.0"

    ready = client.get("/api/v1/readiness", headers={"X-Request-ID": request_id})
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["database"]["ready"] is True
    assert all(component["hard_dependency"] is False for component in body["integrations"].values())
    rendered = json.dumps(body)
    assert "OPENAI_API_KEY" not in rendered
    assert "sqlite:///" not in rendered
    assert "/mnt/data" not in rendered


def test_openapi_has_no_raw_private_pdf_download_route(wave14_full_state) -> None:
    paths = wave14_full_state["client"].get("/openapi.json").json()["paths"]
    lowered = "\n".join(paths).lower()
    assert "download" not in lowered
    assert "raw-pdf" not in lowered
    assert "source-document/{" not in lowered
