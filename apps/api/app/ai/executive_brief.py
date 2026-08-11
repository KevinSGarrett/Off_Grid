from __future__ import annotations

from typing import Any, Mapping

from app.ai.service import OpenAIIntelligenceService
from app.ai.types import AIRunResult


class ExecutiveBriefGenerator:
    """Grounded six-question synthesis facade; final employer export remains human-reviewed."""

    def __init__(self, service: OpenAIIntelligenceService):
        self.service = service

    def generate(self, evidence_context: Mapping[str, Any]) -> AIRunResult:
        return self.service.generate_executive_brief(evidence_context)
