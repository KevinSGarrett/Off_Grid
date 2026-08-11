from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ai.budget import estimate_usage_cost
from app.ai.config import load_openai_config
from app.ai.evidence import EvidenceCatalog
from app.ai.grounding import GroundingValidator
from app.ai.schemas import GroundedClaim, SemanticProjectAnalysis, strict_response_format
from app.ai.service import OpenAIIntelligenceService
from app.ai.tools import ReadOnlyCommercialToolRegistry
from app.ai.types import AIRunStatus, GroundingStatus, UsageMetrics
from app.models import AIClaim, AIUsage, Base, PromptRun, SourceDocument, SourceEvidence, SourceObservation
from app.persistence.database import build_engine
from app.domain.states import EvidenceClassification, MaskingPolicy, PIIClass, ValueType

ROOT = Path(__file__).resolve().parents[2]


def _session() -> Session:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_evidence(session: Session) -> tuple[str, str]:
    from datetime import datetime, timezone
    from app.models import Project

    project = Project(
        canonical_name="Test Project",
        normalized_name="test project",
        canonical_key="test-project",
        source_system="constructconnect",
        external_id="test-1",
    )
    session.add(project)
    session.flush()
    doc = SourceDocument(
        source_type="CONSTRUCTCONNECT_PDF",
        source_system="constructconnect",
        original_filename="test.pdf",
        content_sha256="a" * 64,
        blob_ref="private/test.pdf",
        imported_at=datetime.now(timezone.utc),
        is_private=True,
    )
    session.add(doc)
    session.flush()
    obs = SourceObservation(
        document_id=doc.id,
        project_id=project.id,
        field_name="scope",
        value_type=ValueType.TEXT,
        raw_value="Site work and paving for a data center.",
        normalized_text="Site work and paving for a data center.",
        observation_fingerprint="b" * 64,
        evidence_classification=EvidenceClassification.EXPLICIT,
    )
    session.add(obs)
    session.flush()
    ev = SourceEvidence(
        document_id=doc.id,
        observation_id=obs.id,
        page_number=1,
        excerpt="Site work and paving for a data center.",
        evidence_fingerprint="c" * 64,
        classification=EvidenceClassification.EXPLICIT,
        pii_class=PIIClass.NONE,
        demo_masking_policy=MaskingPolicy.NONE,
        is_permitted_for_decision=True,
    )
    session.add(ev)
    session.commit()
    return str(project.id), EvidenceCatalog.source_ref(ev.id)


def test_openai_config_safe_defaults_and_verified_model_routes() -> None:
    cfg = load_openai_config(ROOT / "config/openai.yaml")
    assert cfg.version == "openai-intelligence-1.0"
    assert cfg.enabled is False
    assert cfg.research_enabled is False
    assert cfg.raw_documents is False
    assert cfg.store_responses is False
    assert cfg.max_output_tokens == 3000
    assert cfg.model_routes["fast"].model_id == "gpt-5.6-luna"
    assert cfg.model_routes["reasoning"].model_id == "gpt-5.6-terra"
    assert cfg.model_routes["research"].model_id == "gpt-5.6-terra"


def test_strict_structured_output_contract_uses_responses_json_schema() -> None:
    fmt = strict_response_format(SemanticProjectAnalysis, name="semantic-project-analysis-1.0")
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["name"] == "semantic-project-analysis-1_0"
    schema = fmt["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "schema_version",
        "summary",
        "claims",
        "unknowns",
        "contradictions",
        "recommended_validation",
    }


def test_grounding_validator_accepts_existing_evidence_and_rejects_fake_id() -> None:
    session = _session()
    _project_id, evidence_ref = _seed_evidence(session)
    validator = GroundingValidator(EvidenceCatalog(session), high_risk_claim_types={"equipment_quantity"})
    valid = GroundedClaim(
        claim_id="c1",
        claim_type="project_type",
        claim_text="The evidence supports a data-center classification.",
        classification="DERIVED",
        evidence_ids=[evidence_ref],
        rationale="Source scope names a data center.",
    )
    invalid = valid.model_copy(update={"claim_id": "c2", "evidence_ids": ["src:00000000-0000-0000-0000-000000000000"]})
    assert validator.validate([valid]).status is GroundingStatus.VALID
    report = validator.validate([invalid])
    assert report.status is GroundingStatus.UNSUPPORTED
    assert "unknown evidence id" in report.issues[0].reason
    session.close()


def test_grounding_validator_rejects_invented_equipment_quantity() -> None:
    session = _session()
    _project_id, evidence_ref = _seed_evidence(session)
    validator = GroundingValidator(EvidenceCatalog(session), high_risk_claim_types={"equipment_quantity"})
    claim = GroundedClaim(
        claim_id="q1",
        claim_type="equipment_quantity",
        claim_text="Stafford will require 18 KVT units.",
        classification="INFERRED",
        evidence_ids=[evidence_ref],
        rationale="This is intentionally unsupported adversarial output.",
    )
    report = validator.validate([claim])
    assert report.status is GroundingStatus.UNSUPPORTED
    assert "18" in report.issues[0].reason
    session.close()


def test_unknown_claim_may_have_no_evidence_but_may_not_cite_fake_evidence() -> None:
    session = _session()
    _seed_evidence(session)
    validator = GroundingValidator(EvidenceCatalog(session))
    unknown = GroundedClaim(
        claim_id="u1",
        claim_type="rental_provider",
        claim_text="The current rental provider is unknown.",
        classification="UNKNOWN",
        evidence_ids=[],
        rationale="No evidence establishes a provider.",
    )
    assert validator.validate([unknown]).is_valid
    fake = unknown.model_copy(update={"claim_id": "u2", "evidence_ids": ["ext:00000000-0000-0000-0000-000000000000"]})
    assert validator.validate([fake]).status is GroundingStatus.UNSUPPORTED
    session.close()


def test_evidence_backed_conflicted_claim_is_valid_but_preserves_conflict_status() -> None:
    session = _session()
    _project_id, evidence_ref = _seed_evidence(session)
    validator = GroundingValidator(EvidenceCatalog(session))
    claim = GroundedClaim(
        claim_id="conflict-1",
        claim_type="source_conflict",
        claim_text="The current source state contains a conflict that requires validation.",
        classification="CONFLICTED",
        evidence_ids=[evidence_ref],
        rationale="The cited source supports exposing the conflict without resolving it.",
    )
    report = validator.validate([claim])
    assert report.status is GroundingStatus.CONFLICTED
    assert report.is_valid
    assert report.issues == ()
    session.close()


def test_read_only_commercial_tool_registry_has_no_write_or_mutation_tools() -> None:
    session = _session()
    registry = ReadOnlyCommercialToolRegistry(session)
    forbidden = {"create", "update", "delete", "sync", "send", "write", "merge", "verify"}
    assert registry.names
    for name in registry.names:
        lowered = name.lower()
        assert not any(token in lowered for token in forbidden)
    for definition in registry.definitions():
        assert definition["type"] == "function"
        assert definition["strict"] is True
        assert definition["parameters"]["additionalProperties"] is False
    session.close()


def test_openai_key_is_not_referenced_by_frontend_source() -> None:
    web_root = ROOT / "apps/web"
    content = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in web_root.rglob("*")
        if path.is_file() and path.suffix in {".ts", ".tsx", ".js", ".jsx", ".html"}
    )
    assert "OPENAI_API_KEY" not in content


def test_estimated_cost_uses_configured_model_pricing() -> None:
    cfg = load_openai_config(ROOT / "config/openai.yaml")
    luna = cfg.model_routes["fast"]
    cost = estimate_usage_cost(
        luna,
        UsageMetrics(input_tokens=1000, cached_input_tokens=200, output_tokens=500),
    )
    assert cost == Decimal("0.003820")


def test_research_mode_is_off_by_default_and_preview_only_when_enabled() -> None:
    session = _session()
    cfg = load_openai_config(ROOT / "config/openai.yaml")
    service = OpenAIIntelligenceService(session, config=cfg)
    assert service.preview_research_request("Stafford project leadership")["enabled"] is False
    enabled = replace(cfg, research_enabled=True)
    preview = OpenAIIntelligenceService(session, config=enabled).preview_research_request("Stafford project leadership")
    assert preview["enabled"] is True
    assert preview["external_request_executed"] is False
    assert preview["request"]["tools"] == [{"type": "web_search"}]
    session.close()


def test_disabled_openai_service_returns_graceful_fallback_without_prompt_run() -> None:
    session = _session()
    project_id, _evidence_ref = _seed_evidence(session)
    cfg = load_openai_config(ROOT / "config/openai.yaml")
    result = OpenAIIntelligenceService(session, config=cfg).analyze_project(__import__("uuid").UUID(project_id))
    assert result.status is AIRunStatus.DISABLED
    assert result.external_request_executed is False
    assert session.scalar(sa.select(sa.func.count()).select_from(PromptRun)) == 0
    session.close()


def test_executive_brief_schema_requires_six_questions_and_unknown_discipline() -> None:
    from pydantic import ValidationError
    from app.ai.schemas import ExecutiveBriefOutput

    supported_claim = {
        "claim_id": "c1",
        "claim_type": "fact",
        "claim_text": "Supported fact.",
        "classification": "DERIVED",
        "evidence_ids": ["src:00000000-0000-0000-0000-000000000001"],
        "rationale": "example",
    }
    unknown_claim = {
        "claim_id": "u1",
        "claim_type": "unknown",
        "claim_text": "Unknown.",
        "classification": "UNKNOWN",
        "evidence_ids": [],
        "rationale": "absent evidence",
    }
    sections = [
        {"question_number": n, "answer": "UNKNOWN" if n == 2 else "answer", "claims": [unknown_claim] if n == 2 else [supported_claim], "status": "UNKNOWN" if n == 2 else "SUPPORTED"}
        for n in range(1, 7)
    ]
    parsed = ExecutiveBriefOutput.model_validate(
        {"schema_version": "executive-brief-1.0", "title": "Brief", "sections": sections, "limitations": []}
    )
    assert len(parsed.sections) == 6
    with pytest.raises(ValidationError):
        ExecutiveBriefOutput.model_validate(
            {"schema_version": "executive-brief-1.0", "title": "Brief", "sections": sections[:5], "limitations": []}
        )
    bad = list(sections)
    bad[1] = {"question_number": 2, "answer": "UNKNOWN", "claims": [supported_claim], "status": "UNKNOWN"}
    with pytest.raises(ValidationError):
        ExecutiveBriefOutput.model_validate(
            {"schema_version": "executive-brief-1.0", "title": "Brief", "sections": bad, "limitations": []}
        )


def test_wave11_official_api_verification_record_exists() -> None:
    record = (ROOT / "research/WAVE_11_OPENAI_API_VERIFICATION.md").read_text(encoding="utf-8")
    assert "Responses API" in record
    assert "gpt-5.6-luna" in record
    assert "gpt-5.6-terra" in record
    assert "structured-outputs" in record
    assert "function-calling" in record
