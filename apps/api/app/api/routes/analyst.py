from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.service import OpenAIIntelligenceService
from app.api.dependencies import get_session
from app.api.serialization import jsonable
from app.models import Project

router = APIRouter(tags=["ai-intelligence"])


class AnalystQuery(BaseModel):
    project_id: UUID
    question: str = Field(min_length=3, max_length=4000)
    # The public ECS gateway has a shorter response window than a bounded Sol
    # analysis can require. Keep Sol available explicitly, but make omitted
    # requests use the gateway-safe Terra path.
    mode: Literal["FAST", "STANDARD", "DEEP"] = "FAST"
    conversation_context: list[dict[str, object]] = Field(default_factory=list, max_length=4)


class ExecutiveBriefRequest(BaseModel):
    context: dict[str, object]


@router.post("/analyst/query")
def analyst_query(payload: AnalystQuery, session: Session = Depends(get_session)) -> dict[str, object]:
    if session.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(payload.project_id)})
    result = OpenAIIntelligenceService(session).answer_commercial_question(
        project_id=payload.project_id,
        question=payload.question,
        mode=payload.mode,
        conversation_context=tuple(payload.conversation_context),
    )
    return {
        "status": result.status.value,
        "task": result.task,
        "model_id": result.model_id,
        "answer": jsonable(result.parsed),
        "grounding": jsonable(result.grounding),
        "fallback_reason": result.fallback_reason,
        "external_request_executed": result.external_request_executed,
        "estimated_cost_usd": str(result.estimated_cost_usd),
        "repair_attempted": result.repair_attempted,
        "latency_ms": result.latency_ms,
        "tool_rounds": result.tool_rounds,
        "cache_hit": result.cache_hit,
        "usage": jsonable(result.usage),
    }


@router.post("/analyst/query/stream")
def analyst_query_stream(payload: AnalystQuery, session: Session = Depends(get_session)) -> StreamingResponse:
    if session.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(payload.project_id)})

    def event_stream() -> Iterator[str]:
        yield "event: progress\ndata: " + json.dumps({"stage": "packet", "message": "Building grounded analysis packet"}) + "\n\n"
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="analyst-stream") as executor:
            future = executor.submit(
                OpenAIIntelligenceService(session).answer_commercial_question,
                project_id=payload.project_id,
                question=payload.question,
                mode=payload.mode,
                conversation_context=tuple(payload.conversation_context),
            )
            heartbeat = 0
            while True:
                try:
                    result = future.result(timeout=10)
                    break
                except FutureTimeoutError:
                    heartbeat += 1
                    yield "event: progress\ndata: " + json.dumps(
                        {
                            "stage": "analysis",
                            "message": "Grounded analysis is still running",
                            "heartbeat": heartbeat,
                        }
                    ) + "\n\n"
        safe_payload = {
            "status": result.status.value,
            "task": result.task,
            "model_id": result.model_id,
            "answer": jsonable(result.parsed),
            "grounding": jsonable(result.grounding),
            "fallback_reason": result.fallback_reason,
            "external_request_executed": result.external_request_executed,
            "estimated_cost_usd": str(result.estimated_cost_usd),
            "repair_attempted": result.repair_attempted,
            "latency_ms": result.latency_ms,
            "tool_rounds": result.tool_rounds,
            "cache_hit": result.cache_hit,
            "usage": jsonable(result.usage),
        }
        yield "event: validated\ndata: " + json.dumps(safe_payload, default=str) + "\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/executive-brief/generate")
def executive_brief(payload: ExecutiveBriefRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    result = OpenAIIntelligenceService(session).generate_executive_brief(payload.context)
    return {
        "status": result.status.value,
        "task": result.task,
        "model_id": result.model_id,
        "brief": jsonable(result.parsed),
        "grounding": jsonable(result.grounding),
        "fallback_reason": result.fallback_reason,
        "external_request_executed": result.external_request_executed,
        "estimated_cost_usd": str(result.estimated_cost_usd),
    }
