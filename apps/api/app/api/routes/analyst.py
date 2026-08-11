from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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


class ExecutiveBriefRequest(BaseModel):
    context: dict[str, object]


@router.post("/analyst/query")
def analyst_query(payload: AnalystQuery, session: Session = Depends(get_session)) -> dict[str, object]:
    if session.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(payload.project_id)})
    result = OpenAIIntelligenceService(session).answer_commercial_question(project_id=payload.project_id, question=payload.question)
    return {
        "status": result.status.value,
        "task": result.task,
        "model_id": result.model_id,
        "answer": jsonable(result.parsed),
        "grounding": jsonable(result.grounding),
        "fallback_reason": result.fallback_reason,
        "external_request_executed": result.external_request_executed,
        "estimated_cost_usd": str(result.estimated_cost_usd),
    }


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
