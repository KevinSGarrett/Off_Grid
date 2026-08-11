from __future__ import annotations

from uuid import UUID

from app.domain.states import AIClaimStatus, EvidenceClassification, ValidationState
from app.schemas.common import EntityRead


class AIClaimRead(EntityRead):
    prompt_run_id: UUID
    project_id: UUID | None = None
    organization_id: UUID | None = None
    person_id: UUID | None = None
    claim_type: str
    claim_text: str
    classification: EvidenceClassification
    validation_state: ValidationState
    status: AIClaimStatus
    accepted_observation_id: UUID | None = None
    rejection_reason: str | None = None
