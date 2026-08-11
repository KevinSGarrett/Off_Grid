from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.budget import DailyBudgetGuard, estimate_request_cost, estimate_usage_cost
from app.ai.config import OpenAIIntelligenceConfig, load_openai_config
from app.ai.evidence import EvidenceCatalog
from app.ai.grounding import GroundingValidator
from app.ai.prompts import load_prompt
from app.ai.schemas import (
    CommercialAnalystAnswer,
    ExecutiveBriefOutput,
    GroundedClaim,
    SemanticProjectAnalysis,
    strict_response_format,
)
from app.ai.tools import ReadOnlyCommercialToolRegistry
from app.ai.transport import OfficialOpenAITransport, OpenAITransport
from app.ai.types import (
    AIRunResult,
    AIRunStatus,
    GroundingReport,
    OpenAIResponseEnvelope,
    UsageMetrics,
)
from app.core.settings import settings
from app.domain.states import AIClaimStatus, EvidenceClassification, RunStatus, ValidationState
from app.models import AIClaim, AIClaimEvidence, AIUsage, PromptRun

T = TypeVar("T", bound=BaseModel)


class OpenAIIntelligenceService:
    """Controlled Responses API layer with strict outputs, grounding, budget and fallback."""

    def __init__(
        self,
        session: Session,
        *,
        config: OpenAIIntelligenceConfig | None = None,
        transport: OpenAITransport | None = None,
    ) -> None:
        self.session = session
        self.config = config or load_openai_config()
        self.catalog = EvidenceCatalog(session)
        self.grounding = GroundingValidator(
            self.catalog,
            high_risk_claim_types=self.config.safety.get("high_risk_claim_types", ()),
        )
        self.transport = transport or self._default_transport()

    def _default_transport(self) -> OpenAITransport | None:
        if not self.config.enabled or not settings.openai_api_key:
            return None
        return OfficialOpenAITransport(
            api_key=settings.openai_api_key,
            max_retries=self.config.max_retries,
            timeout_seconds=self.config.timeout_seconds,
        )

    def build_project_analysis_request(self, project_id: UUID) -> tuple[dict[str, Any], tuple[str, ...]]:
        task_cfg, route = self.config.route_for_task("project_analysis")
        prompt = load_prompt(task_cfg.prompt_name, task_cfg.prompt_version)
        packet = self.catalog.project_packet(project_id)
        payload = {
            "project_id": str(project_id),
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "excerpt": item.excerpt,
                    "page_number": item.page_number,
                    "source_classification": item.classification,
                }
                for item in packet
            ],
            "rules": {
                "do_not_self_declare_explicit_or_verified": True,
                "factual_and_inferred_claims_require_evidence_ids": True,
                "unknowns_must_remain_unknown_when_evidence_is_absent": True,
            },
        }
        request = self._base_request(
            route=route,
            prompt_text=prompt.text,
            input_payload=payload,
            output_model=SemanticProjectAnalysis,
            schema_name=task_cfg.output_schema,
        )
        return request, tuple(item.evidence_id for item in packet)

    def analyze_project(self, project_id: UUID) -> AIRunResult:
        request, _refs = self.build_project_analysis_request(project_id)
        return self._execute_structured(
            task="project_analysis",
            request=request,
            output_model=SemanticProjectAnalysis,
            subject_project_id=project_id,
        )

    def answer_commercial_question(self, *, project_id: UUID, question: str) -> AIRunResult:
        task_cfg, route = self.config.route_for_task("commercial_analyst")
        prompt = load_prompt(task_cfg.prompt_name, task_cfg.prompt_version)
        tools = ReadOnlyCommercialToolRegistry(self.session)
        request = self._base_request(
            route=route,
            prompt_text=prompt.text,
            input_payload={"project_id": str(project_id), "question": question},
            output_model=CommercialAnalystAnswer,
            schema_name=task_cfg.output_schema,
        )
        request["tools"] = tools.definitions()
        return self._execute_structured(
            task="commercial_analyst",
            request=request,
            output_model=CommercialAnalystAnswer,
            subject_project_id=project_id,
            tool_registry=tools,
        )

    def generate_executive_brief(self, context: Mapping[str, Any]) -> AIRunResult:
        task_cfg, route = self.config.route_for_task("executive_brief")
        prompt = load_prompt(task_cfg.prompt_name, task_cfg.prompt_version)
        request = self._base_request(
            route=route,
            prompt_text=prompt.text,
            input_payload=dict(context),
            output_model=ExecutiveBriefOutput,
            schema_name=task_cfg.output_schema,
        )
        return self._execute_structured(
            task="executive_brief",
            request=request,
            output_model=ExecutiveBriefOutput,
        )

    def preview_research_request(self, query: str) -> Mapping[str, Any]:
        if not self.config.research_enabled:
            return {
                "enabled": False,
                "external_request_executed": False,
                "reason": "OPENAI_RESEARCH_ENABLED=false",
            }
        task_cfg, route = self.config.route_for_task("research")
        prompt = load_prompt(task_cfg.prompt_name, task_cfg.prompt_version)
        return {
            "enabled": True,
            "external_request_executed": False,
            "request": {
                "model": route.model_id,
                "instructions": prompt.text,
                "input": query,
                "tools": [{"type": "web_search"}],
                "reasoning": {"effort": route.reasoning_effort},
                "store": self.config.store_responses,
            },
        }

    def _base_request(
        self,
        *,
        route,
        prompt_text: str,
        input_payload: Mapping[str, Any],
        output_model: type[BaseModel],
        schema_name: str,
    ) -> dict[str, Any]:
        return {
            "model": route.model_id,
            "instructions": prompt_text,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(input_payload, sort_keys=True, default=str),
                        }
                    ],
                }
            ],
            "text": {"format": strict_response_format(output_model, name=schema_name)},
            "reasoning": {"effort": route.reasoning_effort},
            "max_output_tokens": self.config.max_output_tokens,
            "store": self.config.store_responses,
        }

    def _execute_structured(
        self,
        *,
        task: str,
        request: dict[str, Any],
        output_model: type[T],
        subject_project_id: UUID | None = None,
        tool_registry: ReadOnlyCommercialToolRegistry | None = None,
    ) -> AIRunResult:
        if not self.config.enabled:
            return AIRunResult(
                status=AIRunStatus.DISABLED,
                task=task,
                model_id=None,
                prompt_run_id=None,
                parsed=None,
                grounding=None,
                estimated_cost_usd=Decimal("0"),
                fallback_reason="OPENAI_ENABLED=false; deterministic core remains available.",
                external_request_executed=False,
            )
        if self.transport is None:
            return AIRunResult(
                status=AIRunStatus.DISABLED,
                task=task,
                model_id=request.get("model"),
                prompt_run_id=None,
                parsed=None,
                grounding=None,
                estimated_cost_usd=Decimal("0"),
                fallback_reason="OpenAI is enabled but no live transport/API key is configured.",
                external_request_executed=False,
            )

        task_cfg, route = self.config.route_for_task(task)
        prompt = load_prompt(task_cfg.prompt_name, task_cfg.prompt_version)
        guard = DailyBudgetGuard(self.session, self.config.daily_budget_usd)
        preflight = estimate_request_cost(
            route,
            request,
            max_output_tokens=self.config.max_output_tokens,
        )
        if not guard.allows(preflight):
            return AIRunResult(
                status=AIRunStatus.BUDGET_BLOCKED,
                task=task,
                model_id=route.model_id,
                prompt_run_id=None,
                parsed=None,
                grounding=None,
                estimated_cost_usd=Decimal("0"),
                fallback_reason=(
                    f"Daily OpenAI budget guard blocked an estimated ${preflight} request; "
                    "deterministic core remains available."
                ),
                external_request_executed=False,
            )

        input_hash = hashlib.sha256(
            json.dumps(request, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        run = PromptRun(
            task=task,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            model_id=route.model_id,
            input_hash=input_hash,
            status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()

        started = time.perf_counter()
        total_usage = UsageMetrics()
        final_envelope: OpenAIResponseEnvelope | None = None
        current_request = dict(request)
        tool_calls_used: list[str] = []
        try:
            for round_index in range(self.config.max_tool_rounds + 1):
                envelope = self.transport.create_response(current_request)
                total_usage = UsageMetrics(
                    input_tokens=total_usage.input_tokens + envelope.usage.input_tokens,
                    output_tokens=total_usage.output_tokens + envelope.usage.output_tokens,
                    cached_input_tokens=(
                        total_usage.cached_input_tokens + envelope.usage.cached_input_tokens
                    ),
                )
                if not envelope.function_calls:
                    final_envelope = envelope
                    break
                if tool_registry is None:
                    raise ValueError("Model requested tools but no read-only tool registry was supplied")
                if round_index >= self.config.max_tool_rounds:
                    raise ValueError("Commercial Analyst exceeded configured tool-call rounds")
                tool_outputs = []
                for call in envelope.function_calls:
                    result = tool_registry.call(call.name, call.arguments)
                    tool_calls_used.append(call.name)
                    tool_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(result, sort_keys=True, default=str),
                        }
                    )
                current_input = list(current_request.get("input") or [])
                current_input.extend(envelope.output_items)
                current_input.extend(tool_outputs)
                current_request = dict(current_request)
                current_request["input"] = current_input
            if final_envelope is None:
                raise ValueError("OpenAI response did not reach a final structured output")

            parsed = output_model.model_validate_json(final_envelope.output_text)
            if isinstance(parsed, CommercialAnalystAnswer):
                # Tool-use provenance comes from the application loop, never from model self-report.
                parsed = parsed.model_copy(update={"tool_calls_used": tool_calls_used})
            claims = self._claims_from(parsed)
            grounding = self.grounding.validate(claims)
            cost = estimate_usage_cost(route, total_usage)
            run.response_id = final_envelope.response_id
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            run.completed_at = datetime.now(timezone.utc)
            run.status = RunStatus.SUCCEEDED if grounding.is_valid else RunStatus.PARTIAL
            self.session.add(
                AIUsage(
                    prompt_run_id=run.id,
                    input_tokens=total_usage.input_tokens,
                    output_tokens=total_usage.output_tokens,
                    cached_input_tokens=total_usage.cached_input_tokens,
                    estimated_cost_usd=cost,
                )
            )
            self._persist_claims(
                prompt_run=run,
                claims=claims,
                grounding=grounding,
                project_id=subject_project_id,
            )
            self.session.commit()
            return AIRunResult(
                status=(AIRunStatus.SUCCEEDED if grounding.is_valid else AIRunStatus.GROUNDING_REJECTED),
                task=task,
                model_id=final_envelope.model_id or route.model_id,
                prompt_run_id=run.id,
                parsed=parsed,
                grounding=grounding,
                estimated_cost_usd=cost,
                fallback_reason=(None if grounding.is_valid else "GroundingValidator rejected unsupported claims."),
                external_request_executed=isinstance(self.transport, OfficialOpenAITransport),
            )
        except Exception as exc:
            # The broad catch is intentional at the provider boundary: the deterministic core degrades
            # gracefully. Domain code never treats a provider failure as a reason to corrupt state.
            run.status = RunStatus.FAILED
            run.error_code = type(exc).__name__
            run.error_detail = str(exc)[:2000]
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            run.completed_at = datetime.now(timezone.utc)
            self.session.commit()
            return AIRunResult(
                status=AIRunStatus.FAILED,
                task=task,
                model_id=route.model_id,
                prompt_run_id=run.id,
                parsed=None,
                grounding=None,
                estimated_cost_usd=Decimal("0"),
                fallback_reason=f"OpenAI capability failed safely: {type(exc).__name__}: {exc}",
                external_request_executed=isinstance(self.transport, OfficialOpenAITransport),
            )

    @staticmethod
    def _claims_from(parsed: BaseModel) -> list[GroundedClaim]:
        if hasattr(parsed, "claims"):
            return list(getattr(parsed, "claims"))
        if isinstance(parsed, ExecutiveBriefOutput):
            return [claim for section in parsed.sections for claim in section.claims]
        return []

    def _persist_claims(
        self,
        *,
        prompt_run: PromptRun,
        claims: list[GroundedClaim],
        grounding: GroundingReport,
        project_id: UUID | None,
    ) -> None:
        issue_by_claim = {issue.claim_id: issue.reason for issue in grounding.issues}
        for claim in claims:
            supported = claim.claim_id not in issue_by_claim
            row = AIClaim(
                prompt_run_id=prompt_run.id,
                project_id=project_id,
                claim_type=claim.claim_type,
                claim_text=claim.claim_text,
                classification=EvidenceClassification(claim.classification),
                validation_state=(ValidationState.VALID if supported else ValidationState.REQUIRES_REVIEW),
                status=(AIClaimStatus.GROUNDED if supported else AIClaimStatus.REJECTED),
                rejection_reason=issue_by_claim.get(claim.claim_id),
            )
            self.session.add(row)
            self.session.flush()
            if not supported:
                continue
            for evidence_ref in claim.evidence_ids:
                if not evidence_ref.startswith("src:"):
                    continue
                evidence_id = UUID(evidence_ref.split(":", 1)[1])
                self.session.add(AIClaimEvidence(ai_claim_id=row.id, source_evidence_id=evidence_id))
