from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.domain.states import VerificationState


@dataclass(frozen=True)
class PhaseDescriptor:
    source_name: str
    base_name: str
    phase_label: str | None
    phase_start_number: int | None
    phase_end_number: int | None

    @property
    def is_phase(self) -> bool:
        return self.phase_start_number is not None


@dataclass(frozen=True)
class MatchDecision:
    subject_id: UUID | None
    candidate_id: UUID | None
    decision: str
    score: Decimal
    method: str
    deterministic: bool
    rationale: str
    review_required: bool


@dataclass(frozen=True)
class ProjectClusterResult:
    project_group_id: UUID
    canonical_name: str
    member_project_ids: tuple[UUID, ...]
    member_names: tuple[str, ...]
    relationship_ids: tuple[UUID, ...]
    confidence_score: Decimal
    verification_state: VerificationState
    evidence_observation_id: UUID | None
    value_aggregation_allowed: bool
    naive_reported_value_sum: Decimal | None
    rationale: str


@dataclass(frozen=True)
class DuplicatePersonCandidate:
    canonical_person_id: UUID
    duplicate_person_id: UUID
    canonical_name: str
    duplicate_name: str
    decision: str
    match_method: str
    name_similarity: Decimal
    same_individual_email: bool
    same_phone: bool
    shared_generic_email_only: bool
    review_required: bool
    rationale: str


@dataclass(frozen=True)
class ContactRecurrenceSignal:
    person_id: UUID
    person_name: str
    unique_project_count: int
    source_association_count: int
    project_ids: tuple[UUID, ...]
    project_names: tuple[str, ...]
    roles: tuple[str, ...]
    recurrence_band: str
    rental_authority_implied: bool = False


@dataclass(frozen=True)
class AccountActivityBand:
    band: str
    source_row_count: int
    unique_project_count: int


@dataclass(frozen=True)
class AccountIntelligenceResult:
    organization_id: UUID
    canonical_name: str
    source_aliases: tuple[str, ...]
    source_project_rows: int
    source_section_counts: dict[str, int]
    unique_projects: int
    unique_project_geographies: int
    geography_counts: dict[str, int]
    project_type_counts: dict[str, int]
    activity_bands: tuple[AccountActivityBand, ...]
    recurring_contacts: tuple[ContactRecurrenceSignal, ...]
    quality_flag_counts: dict[str, int]
    domain_states: dict[str, str]
    strategic_signal_band: str
    entity_resolution_state: str
    account_recommendation: str
    caveats: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProjectAccountResolutionResult:
    resolution_version: str
    ee_reed_organization_id: UUID
    organization_match: MatchDecision
    stafford_cluster: ProjectClusterResult
    duplicate_people: tuple[DuplicatePersonCandidate, ...]
    account_intelligence: AccountIntelligenceResult
    project_person_links_created: int
    source_continuity_passed: bool = True
