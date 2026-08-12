from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar, TypeVar
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

    _validated_answer_cache: ClassVar[dict[str, AIRunResult]] = {}

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

    def answer_commercial_question(
        self,
        *,
        project_id: UUID,
        question: str,
        mode: str = "STANDARD",
        conversation_context: tuple[Mapping[str, Any], ...] = (),
    ) -> AIRunResult:
        request_started = time.perf_counter()
        task_cfg, route = self.config.route_for_task("commercial_analyst")
        route = self.config.analyst_route(mode)
        prompt = load_prompt(task_cfg.prompt_name, task_cfg.prompt_version)
        tools = ReadOnlyCommercialToolRegistry(self.session)
        packet = self._commercial_analysis_packet(project_id, tools)
        cache_material = json.dumps(
            {
                "project_id": str(project_id),
                "question": " ".join(question.lower().split()),
                "mode": mode.upper(),
                "model": route.model_id,
                "reasoning_effort": route.reasoning_effort,
                "prompt_version": task_cfg.prompt_version,
                "evidence_version": packet["evidence_version"],
                "context": list(conversation_context)[-4:],
            },
            sort_keys=True,
            default=str,
        )
        cache_key = hashlib.sha256(cache_material.encode("utf-8")).hexdigest()
        cached = self._validated_answer_cache.get(cache_key)
        if cached is not None:
            return replace(
                cached,
                estimated_cost_usd=Decimal(0),
                external_request_executed=False,
                repair_attempted=False,
                latency_ms=int((time.perf_counter() - request_started) * 1000),
                tool_rounds=0,
                cache_hit=True,
                usage=UsageMetrics(),
            )
        request = self._base_request(
            route=route,
            prompt_text=prompt.text,
            input_payload={
                "project_id": str(project_id),
                "question": question,
                "analysis_mode": mode.upper(),
                "commercial_analysis_packet": packet,
                "prior_validated_context": list(conversation_context)[-4:],
            },
            output_model=CommercialAnalystAnswer,
            schema_name=task_cfg.output_schema,
        )
        cache_project = hashlib.sha256(str(project_id).encode("utf-8")).hexdigest()[:24]
        request["prompt_cache_key"] = f"offgrid-analyst-v2:{cache_project}"
        request["tools"] = tools.definitions()
        result = self._execute_structured(
            task="commercial_analyst",
            request=request,
            output_model=CommercialAnalystAnswer,
            subject_project_id=project_id,
            tool_registry=tools,
            route_override=route,
        )
        if result.status in {AIRunStatus.SUCCEEDED, AIRunStatus.PARTIAL_VALIDATED}:
            self._validated_answer_cache[cache_key] = result
        return result

    def _commercial_analysis_packet(
        self,
        project_id: UUID,
        tools: ReadOnlyCommercialToolRegistry,
    ) -> dict[str, Any]:
        """Build one compact, sanitized packet so common questions need no tool round."""
        pid = str(project_id)
        sections: dict[str, Any] = {
            "project": tools.call("get_project", json.dumps({"project_id": pid})),
            "assessment": tools.call("get_project_assessment", json.dumps({"project_id": pid})),
            "products": tools.call("get_product_fit", json.dumps({"project_id": pid})),
            "contacts": tools.call("get_contact_candidates", json.dumps({"project_id": pid})),
            "actions": tools.call("get_next_best_actions", json.dumps({"project_id": pid})),
            "crm": tools.call("get_crm_readiness", json.dumps({"project_id": pid})),
            "source_evidence": tools.call("get_project_evidence", json.dumps({"project_id": pid})),
        }
        for key, value in sections.items():
            evidence_id = f"det:{project_id}:{key}"
            self.catalog.register_deterministic(
                evidence_id,
                json.dumps(value, sort_keys=True, default=str),
            )
            if isinstance(value, dict):
                value["deterministic_evidence_id"] = evidence_id
        serialized = json.dumps(sections, sort_keys=True, default=str, separators=(",", ":"))
        return {
            "packet_version": "commercial-analysis-packet-2.0",
            "evidence_version": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            "deterministic_assessment_notice": (
                "Decision support only; not a probability, forecast, verified demand, or authority claim."
            ),
            **sections,
        }

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
            "text": {
                "format": strict_response_format(output_model, name=schema_name),
                "verbosity": self.config.text_verbosity,
            },
            "reasoning": {"effort": route.reasoning_effort},
            "max_output_tokens": self.config.max_output_tokens,
            "store": self.config.store_responses,
            "service_tier": self.config.service_tier,
        }

    def _execute_structured(
        self,
        *,
        task: str,
        request: dict[str, Any],
        output_model: type[T],
        subject_project_id: UUID | None = None,
        tool_registry: ReadOnlyCommercialToolRegistry | None = None,
        route_override=None,
    ) -> AIRunResult:
        if not self.config.enabled:
            return AIRunResult(
                status=AIRunStatus.DISABLED,
                task=task,
                model_id=None,
                prompt_run_id=None,
                parsed=None,
                grounding=None,
                estimated_cost_usd=Decimal(0),
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
                estimated_cost_usd=Decimal(0),
                fallback_reason="OpenAI is enabled but no live transport/API key is configured.",
                external_request_executed=False,
            )

        task_cfg, configured_route = self.config.route_for_task(task)
        route = route_override or configured_route
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
                estimated_cost_usd=Decimal(0),
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
            started_at=datetime.now(UTC),
        )
        self.session.add(run)
        self.session.flush()

        started = time.perf_counter()
        total_usage = UsageMetrics()
        final_envelope: OpenAIResponseEnvelope | None = None
        current_request = dict(request)
        tool_calls_used: list[str] = []
        tool_rounds = 0
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
                tool_rounds += 1
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
            repair_attempted = False
            if isinstance(parsed, CommercialAnalystAnswer) and not grounding.is_valid:
                repair_attempted = True
                repair_request = dict(current_request)
                repair_request.pop("tools", None)
                issues = [
                    {"claim_id": issue.claim_id, "reason": issue.reason}
                    for issue in grounding.issues
                ]
                repair_request["instructions"] = (
                    str(request["instructions"])
                    + "\n\nREPAIR PASS: Correct exactly the validator issues below. Remove any claim "
                    "that cannot be supported. Return a complete v2 object.\n"
                    + json.dumps(issues, sort_keys=True)
                )
                repair_envelope = self.transport.create_response(repair_request)
                total_usage = UsageMetrics(
                    input_tokens=total_usage.input_tokens + repair_envelope.usage.input_tokens,
                    output_tokens=total_usage.output_tokens + repair_envelope.usage.output_tokens,
                    cached_input_tokens=total_usage.cached_input_tokens
                    + repair_envelope.usage.cached_input_tokens,
                )
                repaired = output_model.model_validate_json(repair_envelope.output_text)
                repaired = repaired.model_copy(update={"tool_calls_used": tool_calls_used})
                repaired_claims = self._claims_from(repaired)
                repaired_grounding = self.grounding.validate(repaired_claims)
                final_envelope = repair_envelope
                if repaired_grounding.is_valid:
                    parsed, claims, grounding = repaired, repaired_claims, repaired_grounding
                else:
                    valid_ids = set(repaired_grounding.valid_claim_ids)
                    valid_claims = [claim for claim in repaired_claims if claim.claim_id in valid_ids]
                    parsed = self._validated_analyst_answer(
                        repaired,
                        valid_claims,
                        withheld=True,
                    )
                    claims = valid_claims
                    grounding = repaired_grounding
            if isinstance(parsed, CommercialAnalystAnswer) and grounding.is_valid:
                parsed = self._validated_analyst_answer(parsed, claims, withheld=False)
            cost = estimate_usage_cost(route, total_usage)
            run.response_id = final_envelope.response_id
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            run.completed_at = datetime.now(UTC)
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
                status=(AIRunStatus.SUCCEEDED if grounding.is_valid else AIRunStatus.PARTIAL_VALIDATED),
                task=task,
                model_id=final_envelope.model_id or route.model_id,
                prompt_run_id=run.id,
                parsed=parsed,
                grounding=grounding,
                estimated_cost_usd=cost,
                fallback_reason=(
                    None
                    if grounding.is_valid
                    else "Unsupported material was withheld after the bounded repair pass; only validated claims are shown."
                ),
                external_request_executed=isinstance(self.transport, OfficialOpenAITransport),
                repair_attempted=repair_attempted,
                latency_ms=run.latency_ms,
                tool_rounds=tool_rounds,
                usage=total_usage,
            )
        except Exception as exc:
            # The broad catch is intentional at the provider boundary: the deterministic core degrades
            # gracefully. Domain code never treats a provider failure as a reason to corrupt state.
            run.status = RunStatus.FAILED
            run.error_code = type(exc).__name__
            run.error_detail = str(exc)[:2000]
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            run.completed_at = datetime.now(UTC)
            self.session.commit()
            return AIRunResult(
                status=AIRunStatus.FAILED,
                task=task,
                model_id=route.model_id,
                prompt_run_id=run.id,
                parsed=None,
                grounding=None,
                estimated_cost_usd=Decimal(0),
                fallback_reason=f"OpenAI capability failed safely: {type(exc).__name__}: {exc}",
                external_request_executed=isinstance(self.transport, OfficialOpenAITransport),
            )

    @staticmethod
    def _claims_from(parsed: BaseModel) -> list[GroundedClaim]:
        if hasattr(parsed, "claims"):
            return list(parsed.claims)
        if isinstance(parsed, ExecutiveBriefOutput):
            return [claim for section in parsed.sections for claim in section.claims]
        return []

    @staticmethod
    def _validated_analyst_answer(
        parsed: CommercialAnalystAnswer,
        claims: list[GroundedClaim],
        *,
        withheld: bool,
    ) -> CommercialAnalystAnswer:
        """Construct displayed prose only from claim text and its concise rationale."""
        supported = [claim for claim in claims if claim.classification != "UNKNOWN"]
        unknown_claims = [claim for claim in claims if claim.classification == "UNKNOWN"]
        caveat_markers = (
            "UNKNOWN",
            "UNVERIFIED",
            "MISSING",
            "LIMITATION",
            "CAVEAT",
            "CONFLICT",
            "GAP",
        )
        caveat_claims = [
            claim
            for claim in claims
            if claim.classification in {"UNKNOWN", "CONFLICTED"}
            or any(marker in claim.claim_type.upper() for marker in caveat_markers)
            or any(
                marker in claim.claim_text.upper()
                for marker in (" IS UNKNOWN", " REMAINS UNKNOWN", " UNVERIFIED", " NOT CONFIRMED")
            )
        ]
        if supported:
            paragraphs = [
                f"{claim.claim_text}\nWhy: {claim.rationale}"
                for claim in supported
            ]
            answer = "\n\n".join(paragraphs)
            conclusion = supported[0].claim_text
        else:
            answer = "No material analyst conclusion could be validated from the current evidence."
            conclusion = answer
        if withheld:
            answer += "\n\nSome model-generated material was withheld because it did not pass grounding validation."
        explicitly_supported_next_action = parsed.next_action.strip()
        action_type_markers = (
            "NEXT_ACTION",
            "ACTION_SEQUENCE",
            "CALL_OBJECTIVE",
            "PROCESS_PRIORITY",
            "ADVANCEMENT_TRIGGER",
            "DEPRIORITIZATION_TRIGGER",
            "DEMO_TRIGGER",
            "INVESTIGATION_ROUTE",
        )
        action_claim = next(
            (
                claim
                for claim in supported
                if (
                    claim.claim_text.strip() == explicitly_supported_next_action
                    and any(token in claim.claim_type.upper() for token in action_type_markers)
                )
            ),
            None,
        )
        if action_claim is None:
            action_claim = next(
                (
                    claim
                    for claim in supported
                    if any(token in claim.claim_type.upper() for token in action_type_markers)
                ),
                None,
            )
        next_action = action_claim.claim_text if action_claim is not None else conclusion
        trigger_claims = [
            claim
            for claim in claims
            if any(
                token in claim.claim_type.upper()
                for token in (
                    "ACTION",
                    "CALL_",
                    "GATE",
                    "RECOMMENDATION",
                    "REQUIREMENT",
                    "TRIGGER",
                )
            )
        ]
        return parsed.model_copy(
            update={
                "answer": answer,
                "direct_conclusion": conclusion,
                "why": [claim.rationale for claim in supported],
                "supporting_evidence": [ref for claim in supported for ref in claim.evidence_ids],
                "caveats": list(dict.fromkeys(claim.claim_text for claim in caveat_claims)),
                "counterevidence_and_conflicts": [
                    claim.claim_text for claim in claims if claim.classification == "CONFLICTED"
                ],
                "decision_changing_unknowns": list(
                    dict.fromkeys(claim.claim_text for claim in caveat_claims)
                ),
                "recommendation_triggers": list(
                    dict.fromkeys(claim.claim_text for claim in trigger_claims)
                ),
                "next_action": next_action,
                "claims": claims,
                "unknowns": list(dict.fromkeys(parsed.unknowns + [claim.claim_text for claim in unknown_claims])),
            }
        )

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
