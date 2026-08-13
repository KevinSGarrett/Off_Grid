from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import httpx
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.config import load_openai_config
from app.ai.service import OpenAIIntelligenceService
from app.ai.types import AIRunStatus
from app.domain.states import IntegrationMode, RunStatus
from app.ingestion.service import ConstructConnectIngestionService
from app.ingestion.constructconnect_company import parse_company_report
from app.ingestion.errors import ParserReconciliationError
from app.ingestion.pdf_adapter import load_pdf
from app.ingestion.types import ReconciliationResult
from app.integrations.apollo import ApolloAdapter
from app.integrations.pipedrive import PipedriveAdapter
from app.main import create_app
from app.models import Base, Organization, PipelineRun, Project, WorkflowException
from app.persistence.database import build_engine, build_session_factory
from app.resilience import RetryPolicy




ROOT = Path(__file__).resolve().parents[2]
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


def test_company_parser_reconciliation_failure_is_quarantined_and_remains_reviewable(tmp_path, monkeypatch) -> None:
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'reconcile-failure.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        parsed = parse_company_report(load_pdf(EE_REED))
        bad = replace(
            parsed,
            reconciliation=ReconciliationResult(
                expected_planning=parsed.reconciliation.expected_planning,
                parsed_planning=parsed.reconciliation.parsed_planning,
                expected_post_bid=parsed.reconciliation.expected_post_bid,
                parsed_post_bid=parsed.reconciliation.parsed_post_bid - 1,
                expected_bidding_role=parsed.reconciliation.expected_bidding_role,
                parsed_bidding_role=parsed.reconciliation.parsed_bidding_role,
            ),
        )
        monkeypatch.setattr("app.ingestion.service.parse_company_report", lambda _payload: bad)
        with pytest.raises(ParserReconciliationError):
            ConstructConnectIngestionService(session).ingest(EE_REED)

        failed = session.scalar(
            sa.select(PipelineRun).where(PipelineRun.status == RunStatus.FAILED).order_by(PipelineRun.started_at.desc())
        )
        assert failed is not None
        assert failed.exception_count == 1
        exception = session.scalar(
            sa.select(WorkflowException).where(WorkflowException.pipeline_run_id == failed.id)
        )
        assert exception is not None
        assert exception.exception_type == "PARSER_RECONCILIATION_FAILURE"
        assert session.scalar(sa.select(sa.func.count()).select_from(Organization)) == 0

class FailingAITransport:
    def create_response(self, request):
        raise TimeoutError("simulated OpenAI timeout")


class CountingPipedriveTransport:
    def __init__(self):
        self.calls = 0

    def request(self, method, path, *, json):
        self.calls += 1
        raise TimeoutError("ambiguous write outcome")


def test_malformed_pdf_fails_safely_and_persists_failure_run(tmp_path) -> None:
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'failure.db'}")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    client = TestClient(create_app(session_factory=factory, demo_mode=False, upload_dir=tmp_path / "uploads"))
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("broken.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert response.status_code == 422
    with factory() as session:
        failed = session.scalars(sa.select(PipelineRun).where(PipelineRun.status == RunStatus.FAILED)).all()
        assert len(failed) == 1
        assert failed[0].correlation_id.startswith("constructconnect-unknown-")
        assert "/mnt/data" not in (failed[0].error_summary or "")
        assert session.scalar(sa.select(sa.func.count()).select_from(Project)) == 0


def test_openai_timeout_degrades_without_corrupting_deterministic_project(wave14_full_state) -> None:
    factory = wave14_full_state["factory"]
    project_id = wave14_full_state["ids"]["project"]
    with factory() as session:
        before = session.get(Project, project_id)
        assert before is not None
        before_state = before.state
        cfg = replace(load_openai_config(), enabled=True, daily_budget_usd=__import__("decimal").Decimal("100"))
        result = OpenAIIntelligenceService(session, config=cfg, transport=FailingAITransport()).analyze_project(project_id)
        assert result.status is AIRunStatus.FAILED
        assert "failed safely" in (result.fallback_reason or "")
        after = session.get(Project, project_id)
        assert after is not None and after.state == before_state


def test_apollo_transient_live_read_retries_then_succeeds(monkeypatch) -> None:
    calls = {"count": 0}

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"people": [{"id": "synthetic-apollo-result"}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def request(self, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] < 3:
                raise httpx.ReadTimeout("simulated transient timeout")
            return FakeResponse()

    monkeypatch.setattr("app.integrations.apollo.httpx.Client", FakeClient)
    adapter = ApolloAdapter(
        mode=IntegrationMode.LIVE,
        api_key="test-key",
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0),
    )
    preview = adapter.preview_search(titles=["Project Manager"], domains=["example.com"])
    result = adapter.search_people(preview, allow_live=True)
    assert calls["count"] == 3
    assert result["people"][0]["id"] == "synthetic-apollo-result"


def test_pipedrive_write_transport_is_not_blindly_retried_after_ambiguous_failure() -> None:
    transport = CountingPipedriveTransport()
    adapter = PipedriveAdapter(
        mode=IntegrationMode.LIVE,
        demo_mode=False,
        credentials_present=True,
        transport=transport,
    )
    try:
        adapter.execute("POST", "/api/v2/organizations", {"name": "Example"}, readiness_passed=True)
    except TimeoutError:
        pass
    else:
        raise AssertionError("expected simulated write failure")
    # Retry belongs at the CRM sync-attempt/idempotency layer, not as an unsafe blind POST loop.
    assert transport.calls == 1
