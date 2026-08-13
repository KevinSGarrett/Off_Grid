from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from app.ai.config import load_openai_config
from app.ai.service import OpenAIIntelligenceService
from app.ai.types import AIRunStatus, FunctionCall, OpenAIResponseEnvelope, UsageMetrics
from app.commercial_workflow.service import CommercialWorkflowService
from app.contact_resolution.service import ContactResolutionService
from app.crm.service import CommercialIntegrationService
from app.ingestion.service import ConstructConnectIngestionService
from app.models import (
    AIClaim,
    AIClaimEvidence,
    AIUsage,
    Base,
    OpportunityAssessment,
    Project,
    PromptRun,
)
from app.persistence.database import build_engine
from app.resolution.service import ProjectAccountResolutionService
from app.scoring.qualification import QualificationService
from sqlalchemy.orm import Session

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
            "schema_version": "commercial-analyst-answer-2.0",
            "answer": "Stafford should remain in pursue/verify because the deterministic pipeline has qualified it while unresolved facts still require validation.",
            "direct_conclusion": "Stafford remains a promising candidate requiring verification.",
            "why": ["The stored Stafford evidence supports project relevance."],
            "supporting_evidence": [evidence_ref],
            "caveats": ["Product need and rental authority remain unverified."],
            "counterevidence_and_conflicts": [],
            "decision_changing_unknowns": ["verified rental authority"],
            "recommendation_triggers": ["Confirm direct lighting or power need."],
            "next_action": "Verify direct site need and decision authority.",
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


class DuplicateEvidenceFakeTransport(ProjectAnalysisFakeTransport):
    def create_response(self, request):
        envelope = super().create_response(request)
        output = json.loads(envelope.output_text)
        evidence_ref = output["claims"][0]["evidence_ids"][0]
        output["claims"][0]["evidence_ids"] = [evidence_ref, evidence_ref]
        return replace(envelope, output_text=json.dumps(output))


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
    ProjectAccountResolutionService(session).run()
    ContactResolutionService(session).run(project_external_id="1007341663")
    CommercialWorkflowService(session).run(project_external_id="1007341663")
    CommercialIntegrationService(session).run("1007341663")
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


def test_duplicate_model_evidence_references_persist_once_without_http_failure() -> None:
    session = _session()
    stafford = _build(session)
    result = OpenAIIntelligenceService(
        session,
        config=_enabled_config(),
        transport=DuplicateEvidenceFakeTransport(),
    ).analyze_project(stafford.id)
    assert result.status is AIRunStatus.SUCCEEDED
    first_claim = session.scalar(
        sa.select(AIClaim)
        .where(
            AIClaim.prompt_run_id == result.prompt_run_id,
            AIClaim.claim_type == "project_character",
        )
    )
    assert first_claim is not None
    links = session.scalars(
        sa.select(AIClaimEvidence).where(AIClaimEvidence.ai_claim_id == first_claim.id)
    ).all()
    assert len(links) == 1
    session.close()


def test_claim_persistence_failure_rolls_back_and_returns_safe_result() -> None:
    session = _session()
    stafford = _build(session)
    service = OpenAIIntelligenceService(
        session,
        config=_enabled_config(),
        transport=ProjectAnalysisFakeTransport(),
    )

    def fail_persistence(**_kwargs) -> None:
        raise ValueError("forced claim persistence failure")

    service._persist_claims = fail_persistence  # type: ignore[method-assign]
    result = service.analyze_project(stafford.id)
    assert result.status is AIRunStatus.FAILED
    assert result.fallback_reason == (
        "OpenAI capability failed safely (ValueError); deterministic core remains available."
    )
    run = session.get(PromptRun, result.prompt_run_id)
    assert run is not None
    assert run.status.value == "FAILED"
    assert run.error_code == "ValueError"
    assert "forced claim persistence failure" in (run.error_detail or "")
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
    assert result.tool_rounds == 1
    assert result.usage == UsageMetrics(input_tokens=800, output_tokens=220)
    assert result.parsed.next_action == result.parsed.direct_conclusion
    assert transport.calls == 2
    assert result.external_request_executed is False
    cached = service.answer_commercial_question(
        project_id=stafford.id,
        question="What is the biggest unresolved issue before commercial progression?",
    )
    assert transport.calls == 2
    assert cached.cache_hit is True
    assert cached.external_request_executed is False
    assert cached.estimated_cost_usd == 0
    assert cached.latency_ms is not None and cached.latency_ms < 100
    assert cached.tool_rounds == 0
    assert cached.usage == UsageMetrics()
    session.close()


def test_safe_projection_uses_supported_gap_and_action_claims_for_display_sections() -> None:
    from app.ai.schemas import CommercialAnalystAnswer, GroundedClaim

    claims = [
        GroundedClaim(
            claim_id="gap",
            claim_type="AUTHORITY_GAP",
            claim_text="Rental authority remains UNKNOWN.",
            classification="DERIVED",
            evidence_ids=["det:test:contacts"],
            rationale="The deterministic contact state says UNKNOWN.",
        ),
        GroundedClaim(
            claim_id="action",
            claim_type="NEXT_ACTION",
            claim_text="Verify equipment responsibility first.",
            classification="DERIVED",
            evidence_ids=["det:test:actions"],
            rationale="The dependency order makes this the first resolvable action.",
        ),
    ]
    parsed = CommercialAnalystAnswer(
        schema_version="commercial-analyst-answer-2.0",
        answer="Unsafe free prose is replaced.",
        direct_conclusion="Unsafe free prose is replaced.",
        why=[],
        supporting_evidence=[],
        caveats=[],
        counterevidence_and_conflicts=[],
        decision_changing_unknowns=[],
        recommendation_triggers=[],
        next_action="Untraceable action.",
        claims=claims,
        unknowns=[],
        tool_calls_used=[],
    )
    projected = OpenAIIntelligenceService._validated_analyst_answer(
        parsed,
        claims,
        withheld=False,
    )
    assert projected.caveats == ["Rental authority remains UNKNOWN."]
    assert projected.decision_changing_unknowns == ["Rental authority remains UNKNOWN."]
    assert projected.recommendation_triggers == ["Verify equipment responsibility first."]
    assert projected.next_action == "Verify equipment responsibility first."


@pytest.mark.parametrize(
    ("claim_type", "claim_text"),
    [
        ("recommended_next_step", "Verify equipment responsibility before advancing."),
        ("Next-step dependency", "Resolve the named workflow dependency first."),
        ("workflow dependency", "Confirm direct lighting or power need before product selection."),
    ],
)
def test_safe_projection_normalizes_supported_action_claim_types(
    claim_type: str,
    claim_text: str,
) -> None:
    from app.ai.schemas import CommercialAnalystAnswer, GroundedClaim

    claims = [
        GroundedClaim(
            claim_id="conclusion",
            claim_type="DIRECT_CONCLUSION",
            claim_text="The opportunity remains a promising candidate.",
            classification="DERIVED",
            evidence_ids=["det:test:assessment"],
            rationale="The current deterministic assessment supports that band.",
        ),
        GroundedClaim(
            claim_id="action",
            claim_type=claim_type,
            claim_text=claim_text,
            classification="DERIVED",
            evidence_ids=["det:test:actions"],
            rationale="The deterministic dependency state supports this action.",
        ),
    ]
    parsed = CommercialAnalystAnswer(
        schema_version="commercial-analyst-answer-2.0",
        answer="Unsafe free prose is replaced.",
        direct_conclusion="Unsafe free prose is replaced.",
        why=[],
        supporting_evidence=[],
        caveats=[],
        counterevidence_and_conflicts=[],
        decision_changing_unknowns=[],
        recommendation_triggers=[],
        next_action=claim_text,
        claims=claims,
        unknowns=[],
        tool_calls_used=[],
    )
    projected = OpenAIIntelligenceService._validated_analyst_answer(
        parsed,
        claims,
        withheld=False,
    )
    assert projected.next_action == claim_text
    assert claim_text in projected.recommendation_triggers


def test_safe_projection_never_displays_unsupported_next_action() -> None:
    from app.ai.schemas import CommercialAnalystAnswer, GroundedClaim

    supported_action = "Verify equipment responsibility before advancing."
    claims = [
        GroundedClaim(
            claim_id="conclusion",
            claim_type="DIRECT_CONCLUSION",
            claim_text="The opportunity remains a promising candidate.",
            classification="DERIVED",
            evidence_ids=["det:test:assessment"],
            rationale="The current deterministic assessment supports that band.",
        ),
        GroundedClaim(
            claim_id="action",
            claim_type="recommended next step",
            claim_text=supported_action,
            classification="DERIVED",
            evidence_ids=["det:test:actions"],
            rationale="The deterministic dependency state supports this action.",
        ),
    ]
    parsed = CommercialAnalystAnswer(
        schema_version="commercial-analyst-answer-2.0",
        answer="Unsafe free prose is replaced.",
        direct_conclusion="Unsafe free prose is replaced.",
        why=[],
        supporting_evidence=[],
        caveats=[],
        counterevidence_and_conflicts=[],
        decision_changing_unknowns=[],
        recommendation_triggers=[],
        next_action="Create a CRM deal now.",
        claims=claims,
        unknowns=[],
        tool_calls_used=[],
    )
    projected = OpenAIIntelligenceService._validated_analyst_answer(
        parsed,
        claims,
        withheld=False,
    )
    assert projected.next_action == supported_action
    assert "Create a CRM deal now." not in projected.model_dump_json()


def test_safe_projection_does_not_treat_transaction_status_or_unknown_as_action() -> None:
    from app.ai.schemas import CommercialAnalystAnswer, GroundedClaim

    claims = [
        GroundedClaim(
            claim_id="conclusion",
            claim_type="DIRECT_CONCLUSION",
            claim_text="CRM progression remains blocked.",
            classification="DERIVED",
            evidence_ids=["det:test:crm"],
            rationale="The deterministic CRM gate is blocked.",
        ),
        GroundedClaim(
            claim_id="transaction",
            claim_type="CRM_TRANSACTION_STATUS",
            claim_text="No CRM transaction was executed.",
            classification="DERIVED",
            evidence_ids=["det:test:crm"],
            rationale="The deterministic integration state is dry-run.",
        ),
        GroundedClaim(
            claim_id="unknown-action",
            claim_type="NEXT_ACTION",
            claim_text="Create a CRM deal now.",
            classification="UNKNOWN",
            evidence_ids=["det:test:crm"],
            rationale="No evidence supports this action.",
        ),
    ]
    parsed = CommercialAnalystAnswer(
        schema_version="commercial-analyst-answer-2.0",
        answer="Unsafe free prose is replaced.",
        direct_conclusion="Unsafe free prose is replaced.",
        why=[],
        supporting_evidence=[],
        caveats=[],
        counterevidence_and_conflicts=[],
        decision_changing_unknowns=[],
        recommendation_triggers=[],
        next_action="Create a CRM deal now.",
        claims=claims,
        unknowns=[],
        tool_calls_used=[],
    )
    projected = OpenAIIntelligenceService._validated_analyst_answer(
        parsed,
        claims,
        withheld=False,
    )
    assert projected.next_action == "CRM progression remains blocked."
    assert projected.recommendation_triggers == []
    assert "Create a CRM deal now." not in projected.answer


def test_safe_projection_humanizes_code_only_supported_action_for_display() -> None:
    from app.ai.schemas import CommercialAnalystAnswer, GroundedClaim

    claims = [
        GroundedClaim(
            claim_id="conclusion",
            claim_type="DIRECT_CONCLUSION",
            claim_text="CRM progression remains blocked.",
            classification="DERIVED",
            evidence_ids=["det:test:crm"],
            rationale="The deterministic CRM gate is blocked.",
        ),
        GroundedClaim(
            claim_id="action",
            claim_type="NEXT_ACTION",
            claim_text="VERIFY_SITE_EQUIPMENT_RESPONSIBILITY",
            classification="DERIVED",
            evidence_ids=["det:test:actions"],
            rationale="This is the first unresolved deterministic dependency.",
        ),
    ]
    parsed = CommercialAnalystAnswer(
        schema_version="commercial-analyst-answer-2.0",
        answer="Unsafe free prose is replaced.",
        direct_conclusion="Unsafe free prose is replaced.",
        why=[],
        supporting_evidence=[],
        caveats=[],
        counterevidence_and_conflicts=[],
        decision_changing_unknowns=[],
        recommendation_triggers=[],
        next_action="VERIFY_SITE_EQUIPMENT_RESPONSIBILITY",
        claims=claims,
        unknowns=[],
        tool_calls_used=[],
    )
    projected = OpenAIIntelligenceService._validated_analyst_answer(
        parsed,
        claims,
        withheld=False,
    )
    assert projected.next_action == "Verify site equipment responsibility."
    assert projected.recommendation_triggers == ["Verify site equipment responsibility."]
    assert "VERIFY_SITE_EQUIPMENT_RESPONSIBILITY" not in projected.answer
    assert projected.claims[1].claim_text == "VERIFY_SITE_EQUIPMENT_RESPONSIBILITY"


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
