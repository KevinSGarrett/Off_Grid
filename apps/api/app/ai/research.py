from __future__ import annotations

from typing import Any, Mapping

from app.ai.service import OpenAIIntelligenceService


class PermissionedResearchMode:
    """Explicit gate for optional OpenAI web-search research.

    Research is disabled by default and is separate from the deterministic stored Wave 8 evidence
    snapshot. Calling preview never executes a network request.
    """

    def __init__(self, service: OpenAIIntelligenceService):
        self.service = service

    def preview(self, query: str) -> Mapping[str, Any]:
        return self.service.preview_research_request(query)
