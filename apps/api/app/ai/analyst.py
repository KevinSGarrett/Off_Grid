from __future__ import annotations

from uuid import UUID

from app.ai.service import OpenAIIntelligenceService
from app.ai.types import AIRunResult


class CommercialAnalyst:
    """Read-only natural-language analyst facade.

    Tool execution is delegated to the service's approved read-only registry. This facade has no
    mutation methods and is not an integration adapter.
    """

    def __init__(self, service: OpenAIIntelligenceService):
        self.service = service

    def answer(self, *, project_id: UUID, question: str) -> AIRunResult:
        return self.service.answer_commercial_question(project_id=project_id, question=question)
