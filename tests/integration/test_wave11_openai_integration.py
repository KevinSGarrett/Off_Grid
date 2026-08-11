from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ai.config import load_openai_config
from app.ai.service import OpenAIIntelligenceService
from app.ai.types import AIRunStatus, FunctionCall, OpenAIResponseEnvelope, UsageMetrics
from app.commercial_workflow.service import Wave09CommercialWorkflowService
from app.contact_resolution.service import Wave08ContactResolutionService
from app.crm.service import Wave10IntegrationService
from app.ingestion.service import ConstructConnectIngestionService
from app.models import AIClaim, AIUsage, Base, OpportunityAssessment, Project, PromptRun
from app.persistence.database import build_engine
from app.resolution.service import Wave07ResolutionService
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


class ProjectAnalysisFakeTransport:
    def __init__(self):
        self.calls = 0

    def create_response(self, request):
        self.calls += 1
        payload = json.loads(request["input"][0]["content"][0]["text"])
        refs = [row["evidence_id"] for row in payload["evidence"]]
        output = {
            "schema_version": "semantic-project-analysis-1.0",
            "summary": "Stafford remains a high-priority project for deterministic commercial validation.",
            "claims": [
                {
                    "claim_id": "stafford-semantic-1",
                    "claim_type": "project_character",
                    "claim_text": "The cited source evidence supports a large data-center construction opportunity.",
                    "classification": "DERIVED",
                    "evidence_ids": refs[:1],
                    "rationale": "The model is restating a bounded source-supported project characteristic.",
                },
                {
                    "claim_id": "stafford-semantic-2",
                    "claim_type": "temporary_lighting_relevance",
                    "claim_text": "Temporary lighting may be commercially relevant and requires validation.",
                    "classification": "INFERRED",
                    "evidence_ids": refs[:2],
                    "rationale": "This is explicitly preserved as an inference, not a source fact.",
                },
                {
                    "claim_id": "stafford-semantic-3",
                    "claim_type": "rental_provider",
                    "claim_text": "The current rental provider is unknown.",
                    "classification": "UNKNOWN",
                    "evidence_ids": [],
                    "rationale": "The supplied source evidence does not identify a rental provider.",
                },
            ],
            "unknowns": ["current rental provider", "verified site equipment authority"],
            "contradictions": [],
            "recommended_validation": ["Verify site lighting/power responsibility."],
        }
        return OpenAIResponseEnvelope(
            response_id="resp_fake_project",
            model_id=request["model"],
            output_text=json.dumps(output),
            usage=UsageMetrics(input_tokens=900, output_tokens=300, cached_input_tokens=100),
        )


class AnalystToolLoopFakeTransport:
    def __init__(self):
        self.calls = 0

    def create_response(self, request):
        self.calls += 1
        if self.calls == 1:
            project_id = json.loads(request["input"][0]["content"][0]["text"])["project_id"]
            call = {
                "type": "function_call",
                "call_id": "call_evidence",
                "name": "get_project_evidence",
                "arguments": json.dumps({"project_id": project_id}),
            }
            return OpenAIResponseEnvelope(
                response_id="resp_tool_1",
                model_id=request["model"],
                output_text="",
                output_items=(call,),
                function_calls=(
                    FunctionCall(
                        call_id="call_evidence",
                        name="get_project_evidence",
                        arguments=call["arguments"],
                    ),
                ),
                usage=UsageMetrics(input_tokens=300, output_tokens=40),
            )
        tool_outputs = [row for row in request["input"] if row.get("type") == "function_call_output"]
        assert tool_outputs
        evidence_rows = json.loads(tool_outputs[-1]["output"])["evidence"]
        evidence_ref = evidence_rows[0]["evidence_id"]
        output = {
            "schema_version": "commercial-analyst-answer-1.0",
            "answer": "Stafford should remain in pursue/verify because the deterministic pipeline has qualified it while unresolved facts still require validation.",
            "claims": [
                {
                    "claim_id": "analyst-1",
                    "claim_type": "project_evidence",
                    "claim_text": "The answer is grounded in the stored Stafford evidence packet.",
                    "classification": "DERIVED",
                    "evidence_ids": [evidence_ref],
                    "rationale": "The analyst used the approved project-evidence tool.",
                }
            ],
            "unknowns": ["verified rental authority"],
            "tool_calls_used": [],
        }
        return OpenAIResponseEnvelope(
            response_id="resp_tool_2",
            model_id=request["model"],
            output_text=json.dumps(output),
            usage=UsageMetrics(input_tokens=500, output_tokens=180),
        )


def _session() -> Session:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _build(session: Session) -> Project:
    ingest = ConstructConnectIngestionService(session)
    ingest.ingest(STAFFORD)
    ingest.ingest(EE_REED)
    stafford = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    assert stafford is not None
    QualificationService(session).evaluate(stafford.id, persist=True)
    Wave07ResolutionService(session).run()
    Wave08ContactResolutionService(session).run()
    Wave09CommercialWorkflowService(session).run()
    Wave10IntegrationService(session).run()
    return stafford


def _enabled_config(*, budget="2.00"):
    base = load_openai_config(ROOT / "config/openai.yaml")
    return replace(base, enabled=True, daily_budget_usd=Decimal(budget))


def test_wave11_project_analysis_uses_real_stafford_evidence_and_persists_provenance() -> None:
    session = _session()
    stafford = _build(session)
    transport = ProjectAnalysisFakeTransport()
    service = OpenAIIntelligenceService(session, config=_enabled_config(), transport=transport)
    request, refs = service.build_project_analysis_request(stafford.id)
    serialized = json.dumps(request)
    assert ".pdf" not in serialized
    assert "333 Commerce Green" not in serialized
    assert refs and all(ref.startswith("src:") for ref in refs)
    assert request["text"]["format"]["strict"] is True
    result = service.analyze_project(stafford.id)
    assert result.status is AIRunStatus.SUCCEEDED
    assert result.external_request_executed is False
    assert result.parsed.schema_version == "semantic-project-analysis-1.0"
    assert result.parsed.claims[-1].classification == "UNKNOWN"
    assert result.grounding and result.grounding.is_valid
    assert transport.calls == 1

    run = session.get(PromptRun, result.prompt_run_id)
    assert run is not None
    assert run.prompt_name == "project_analysis"
    assert run.prompt_version == "v1"
    assert run.model_id == "gpt-5.6-luna"
    assert run.input_hash and len(run.input_hash) == 64
    assert run.response_id == "resp_fake_project"
    usage = session.scalar(sa.select(AIUsage).where(AIUsage.prompt_run_id == run.id))
    assert usage is not None and usage.input_tokens == 900 and usage.output_tokens == 300
    claims = session.scalars(sa.select(AIClaim).where(AIClaim.prompt_run_id == run.id)).all()
    assert len(claims) == 3
    assert all(row.status.value == "GROUNDED" for row in claims)
    session.close()


def test_commercial_analyst_executes_only_approved_read_only_tool_loop() -> None:
    session = _session()
    stafford = _build(session)
    transport = AnalystToolLoopFakeTransport()
    service = OpenAIIntelligenceService(session, config=_enabled_config(), transport=transport)
    result = service.answer_commercial_question(
        project_id=stafford.id,
        question="What is the biggest unresolved issue before commercial progression?",
    )
    assert result.status is AIRunStatus.SUCCEEDED
    assert result.parsed.tool_calls_used == ["get_project_evidence"]
    assert result.parsed.unknowns == ["verified rental authority"]
    assert transport.calls == 2
    assert result.external_request_executed is False
    session.close()


def test_budget_guard_blocks_provider_call_and_preserves_deterministic_assessment() -> None:
    session = _session()
    stafford = _build(session)
    assessment_before = session.scalar(
        sa.select(OpportunityAssessment).where(
            OpportunityAssessment.project_id == stafford.id,
            OpportunityAssessment.is_current.is_(True),
        )
    )
    assert assessment_before is not None
    transport = ProjectAnalysisFakeTransport()
    service = OpenAIIntelligenceService(session, config=_enabled_config(budget="0.000001"), transport=transport)
    result = service.analyze_project(stafford.id)
    assert result.status is AIRunStatus.BUDGET_BLOCKED
    assert transport.calls == 0
    assessment_after = session.get(OpportunityAssessment, assessment_before.id)
    assert assessment_after is not None
    assert assessment_after.commercial_fit_score == assessment_before.commercial_fit_score
    assert session.scalar(sa.select(sa.func.count()).select_from(PromptRun)) == 0
    session.close()


def test_wave11_does_not_execute_real_external_openai_requests() -> None:
    session = _session()
    stafford = _build(session)
    result = OpenAIIntelligenceService(
        session,
        config=_enabled_config(),
        transport=ProjectAnalysisFakeTransport(),
    ).analyze_project(stafford.id)
    assert result.external_request_executed is False
    session.close()
