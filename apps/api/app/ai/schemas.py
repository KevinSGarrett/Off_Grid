from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.states import EvidenceClassification


class StrictAIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GroundedClaim(StrictAIModel):
    claim_id: str
    claim_type: str
    claim_text: str
    classification: Literal[
        EvidenceClassification.DERIVED.value,
        EvidenceClassification.INFERRED.value,
        EvidenceClassification.CONFLICTED.value,
        EvidenceClassification.UNKNOWN.value,
    ]
    evidence_ids: list[str]
    rationale: str


class SemanticProjectAnalysis(StrictAIModel):
    schema_version: Literal["semantic-project-analysis-1.0"]
    summary: str
    claims: list[GroundedClaim]
    unknowns: list[str]
    contradictions: list[str]
    recommended_validation: list[str]


class CommercialAnalystAnswer(StrictAIModel):
    schema_version: Literal["commercial-analyst-answer-2.0"]
    answer: str
    direct_conclusion: str
    why: list[str]
    supporting_evidence: list[str]
    caveats: list[str]
    counterevidence_and_conflicts: list[str]
    decision_changing_unknowns: list[str]
    recommendation_triggers: list[str]
    next_action: str
    claims: list[GroundedClaim]
    unknowns: list[str]
    tool_calls_used: list[str]

    @model_validator(mode="after")
    def answer_must_be_represented_by_claims(self):
        if self.answer.strip() and not self.claims:
            raise ValueError("A substantive analyst answer requires grounded claims")
        return self


class ExecutiveBriefSection(StrictAIModel):
    question_number: int = Field(ge=1, le=6)
    answer: str
    claims: list[GroundedClaim]
    status: Literal["SUPPORTED", "PARTIAL", "UNKNOWN"]

    @model_validator(mode="after")
    def unknown_sections_cannot_smuggle_supported_claims(self):
        if self.status == "UNKNOWN" and any(claim.classification != "UNKNOWN" for claim in self.claims):
            raise ValueError("UNKNOWN brief sections may contain only UNKNOWN claims")
        return self


class ExecutiveBriefOutput(StrictAIModel):
    schema_version: Literal["executive-brief-1.0"]
    title: str
    sections: list[ExecutiveBriefSection]
    limitations: list[str]

    @model_validator(mode="after")
    def require_all_six_assignment_questions(self):
        numbers = [section.question_number for section in self.sections]
        if sorted(numbers) != [1, 2, 3, 4, 5, 6]:
            raise ValueError("Executive Brief must contain exactly questions 1 through 6")
        return self


def strict_response_format(model: type[BaseModel], *, name: str) -> dict[str, object]:
    """Return the Responses API strict JSON-schema format for a Pydantic output model."""
    provider_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    if not provider_name:
        raise ValueError("structured-output schema name must contain an alphanumeric character")
    return {
        "type": "json_schema",
        "name": provider_name,
        "strict": True,
        "schema": model.model_json_schema(),
    }
