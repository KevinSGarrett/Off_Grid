from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.domain.states import ContactState, VerificationState


@dataclass(frozen=True)
class EvidenceDecision:
    attribute: str
    state: VerificationState
    highest_priority: int
    evidence_ids: tuple[UUID, ...]
    source_types: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class ContactScoreFactor:
    key: str
    points: Decimal
    max_points: Decimal
    rationale: str


@dataclass(frozen=True)
class ContactCandidateResult:
    candidate_id: UUID
    person_id: UUID
    person_name: str
    organization_id: UUID | None
    organization_name: str | None
    target_persona: str
    public_role_label: str
    rank: int
    candidate_score: Decimal
    state: ContactState
    employment_state: VerificationState
    project_association_state: VerificationState
    role_relevance_state: VerificationState
    rental_authority_state: VerificationState
    score_factors: tuple[ContactScoreFactor, ...]
    evidence_ids: tuple[UUID, ...]
    recommended_action: str


@dataclass(frozen=True)
class ApolloPreviewPlan:
    mode: str
    search_endpoint: str
    search_payload: dict
    enrichment_endpoint: str
    enrichment_candidate_ids: tuple[UUID, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Wave08ContactResolutionResult:
    contact_resolution_version: str
    persona_version: str
    source_precedence_version: str
    project_id: UUID
    east_coast_organization_id: UUID
    candidates: tuple[ContactCandidateResult, ...]
    external_evidence_count: int
    verification_event_count: int
    authority_verified_count: int
    apollo_preview: ApolloPreviewPlan
    explicit_unknowns: tuple[str, ...]
    research_snapshot_version: str
