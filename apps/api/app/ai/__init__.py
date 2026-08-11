"""Controlled OpenAI intelligence layer.

The package is intentionally separate from deterministic parsing, scoring, identity, workflow,
and integration code. Nothing in this package may directly perform an external business write.
"""

from app.ai.config import OpenAIIntelligenceConfig, load_openai_config
from app.ai.grounding import GroundingValidator
from app.ai.service import OpenAIIntelligenceService

__all__ = [
    "GroundingValidator",
    "OpenAIIntelligenceConfig",
    "OpenAIIntelligenceService",
    "load_openai_config",
]
