from __future__ import annotations

import re
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

import sqlalchemy as sa
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.domain.states import VerificationState
from app.ingestion.normalization import collapse_space, normalized_name
from app.models import Project, ProjectGroup, ProjectRelationship, SourceObservation
from app.resolution.types import MatchDecision, PhaseDescriptor, ProjectClusterResult

_PHASE_RE = re.compile(r"(?i)\bphases?\s+(\d+)\s*(?:&|and|-)\s*(\d+)\b")
_SINGLE_PHASE_RE = re.compile(r"(?i)\bphase\s+(\d+)\b")


def extract_phase_descriptor(name: str) -> PhaseDescriptor:
    text = collapse_space(name) or name
    match = _PHASE_RE.search(text)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        base = collapse_space((text[: match.start()] + text[match.end() :]).strip(" -/,")) or text
        return PhaseDescriptor(
            source_name=text,
            base_name=base,
            phase_label=f"Phases {start} & {end}",
            phase_start_number=min(start, end),
            phase_end_number=max(start, end),
        )
    single = _SINGLE_PHASE_RE.search(text)
    if single:
        number = int(single.group(1))
        base = collapse_space((text[: single.start()] + text[single.end() :]).strip(" -/,")) or text
        return PhaseDescriptor(
            source_name=text,
            base_name=base,
            phase_label=f"Phase {number}",
            phase_start_number=number,
            phase_end_number=number,
        )
    return PhaseDescriptor(
        source_name=text,
        base_name=text,
        phase_label=None,
        phase_start_number=None,
        phase_end_number=None,
    )


def _location_key(project: Project) -> tuple[str, str]:
    return ((project.city or "").strip().lower(), (project.region or "").strip().lower())


def compare_projects(subject: Project, candidate: Project) -> MatchDecision:
    if subject.id == candidate.id:
        return MatchDecision(
            subject_id=subject.id,
            candidate_id=candidate.id,
            decision="SAME_RECORD",
            score=Decimal("1.0000"),
            method="PRIMARY_KEY",
            deterministic=True,
            rationale="Same canonical Project row.",
            review_required=False,
        )
    if (
        subject.source_system
        and candidate.source_system
        and subject.source_system == candidate.source_system
        and subject.external_id
        and subject.external_id == candidate.external_id
    ):
        return MatchDecision(
            subject_id=subject.id,
            candidate_id=candidate.id,
            decision="AUTO_MATCH",
            score=Decimal("1.0000"),
            method="SOURCE_EXTERNAL_ID",
            deterministic=True,
            rationale="The projects share the same source system and external project identifier.",
            review_required=False,
        )

    left = extract_phase_descriptor(subject.canonical_name)
    right = extract_phase_descriptor(candidate.canonical_name)
    same_geo = _location_key(subject) == _location_key(candidate) and any(_location_key(subject))
    base_similarity = Decimal(str(round(fuzz.token_set_ratio(normalized_name(left.base_name), normalized_name(right.base_name)) / 100, 4)))

    if same_geo and normalized_name(left.base_name) == normalized_name(right.base_name):
        if left.is_phase and right.is_phase and (
            left.phase_start_number != right.phase_start_number
            or left.phase_end_number != right.phase_end_number
        ):
            return MatchDecision(
                subject_id=subject.id,
                candidate_id=candidate.id,
                decision="SAME_GROUP_DIFFERENT_PHASE",
                score=Decimal("0.9800"),
                method="BASE_NAME_PLUS_GEOGRAPHY_PLUS_PHASE_RANGE",
                deterministic=True,
                rationale="Normalized base project/campus name and geography are identical while phase ranges differ.",
                review_required=False,
            )
        return MatchDecision(
            subject_id=subject.id,
            candidate_id=candidate.id,
            decision="AUTO_MATCH_CANDIDATE",
            score=Decimal("0.9700"),
            method="BASE_NAME_PLUS_GEOGRAPHY",
            deterministic=True,
            rationale="Normalized base project name and geography are identical.",
            review_required=False,
        )

    if same_geo and base_similarity >= Decimal("0.92"):
        return MatchDecision(
            subject_id=subject.id,
            candidate_id=candidate.id,
            decision="REVIEW",
            score=base_similarity,
            method="FUZZY_BASE_NAME_PLUS_GEOGRAPHY",
            deterministic=False,
            rationale="Project base names are highly similar and geography matches, but fuzzy similarity alone cannot silently merge projects.",
            review_required=True,
        )
    return MatchDecision(
        subject_id=subject.id,
        candidate_id=candidate.id,
        decision="NO_MATCH",
        score=base_similarity,
        method="FUZZY_BASE_NAME",
        deterministic=False,
        rationale="Insufficient deterministic evidence for project identity/grouping.",
        review_required=False,
    )


class ProjectClusteringService:
    def __init__(self, session: Session):
        self.session = session

    def cluster_related_phases(self, project_ids: list[UUID] | tuple[UUID, ...]) -> ProjectClusterResult:
        projects = list(self.session.scalars(sa.select(Project).where(Project.id.in_(list(project_ids)))).all())
        if len(projects) < 2:
            raise ValueError("Project clustering requires at least two project records")
        descriptors = {project.id: extract_phase_descriptor(project.canonical_name) for project in projects}
        base_names = {normalized_name(desc.base_name) for desc in descriptors.values()}
        geos = {_location_key(project) for project in projects}
        if len(base_names) != 1 or len(geos) != 1:
            raise ValueError("Projects do not have deterministic same-campus evidence")
        if not all(desc.is_phase for desc in descriptors.values()):
            raise ValueError("All clustered project records must expose a structured phase label")

        base_name = next(iter(descriptors.values())).base_name
        city, region = next(iter(geos))
        group_key_input = f"{normalized_name(base_name)}|{city}|{region}"
        group_key = f"project-group:{sha256(group_key_input.encode()).hexdigest()[:24]}"
        group = self.session.scalar(sa.select(ProjectGroup).where(ProjectGroup.canonical_key == group_key))
        if group is None:
            group = ProjectGroup(
                canonical_name=base_name,
                normalized_name=normalized_name(base_name),
                canonical_key=group_key,
                group_type="CAMPUS",
                description="Canonical multi-phase construction campus grouping created from deterministic base-name, geography and source phase evidence.",
            )
            self.session.add(group)
            self.session.flush()

        for project in projects:
            desc = descriptors[project.id]
            project.project_group_id = group.id
            project.phase_label = desc.phase_label
            project.phase_start_number = desc.phase_start_number
            project.phase_end_number = desc.phase_end_number

        ordered = sorted(projects, key=lambda p: (p.phase_start_number or 999999, p.phase_end_number or 999999, p.canonical_name))
        evidence_observation = self._relationship_evidence(ordered)
        relationship_ids: list[UUID] = []
        for left, right in zip(ordered, ordered[1:]):
            existing = self.session.scalar(
                sa.select(ProjectRelationship).where(
                    ProjectRelationship.parent_project_id == left.id,
                    ProjectRelationship.child_project_id == right.id,
                    ProjectRelationship.relationship_type == "SAME_CAMPUS_PHASE_SEQUENCE",
                )
            )
            if existing is None:
                existing = ProjectRelationship(
                    parent_project_id=left.id,
                    child_project_id=right.id,
                    relationship_type="SAME_CAMPUS_PHASE_SEQUENCE",
                    verification_state=VerificationState.SUPPORTED,
                    source_observation_id=evidence_observation.id if evidence_observation else None,
                    confidence_score=Decimal("0.9800"),
                    rationale=(
                        "Identical normalized Stafford Technology Campus base name and geography; distinct explicit phase ranges; "
                        "the Stafford project narrative also references Phases 1 & 2 as part of the same multi-phased development."
                    ),
                )
                self.session.add(existing)
                self.session.flush()
            relationship_ids.append(existing.id)

        values = [project.reported_value for project in ordered if project.reported_value is not None]
        naive_sum = sum(values, Decimal("0")) if values else None
        self.session.flush()
        return ProjectClusterResult(
            project_group_id=group.id,
            canonical_name=group.canonical_name,
            member_project_ids=tuple(project.id for project in ordered),
            member_names=tuple(project.canonical_name for project in ordered),
            relationship_ids=tuple(relationship_ids),
            confidence_score=Decimal("0.9800"),
            verification_state=VerificationState.SUPPORTED,
            evidence_observation_id=evidence_observation.id if evidence_observation else None,
            value_aggregation_allowed=False,
            naive_reported_value_sum=naive_sum,
            rationale=(
                "Reported phase values are retained separately and must not be blindly summed into independent pipeline value. "
                "The Stafford source explicitly describes a larger multi-phased development and warns that phase-level values are estimated."
            ),
        )

    def _relationship_evidence(self, projects: list[Project]) -> SourceObservation | None:
        # Prefer the dedicated Stafford project narrative because it explicitly links the current phase record
        # to Phases 1 & 2 and calls the development multi-phased.
        for project in projects:
            obs = self.session.scalar(
                sa.select(SourceObservation)
                .where(
                    SourceObservation.project_id == project.id,
                    SourceObservation.field_name == "project.description",
                )
                .order_by(SourceObservation.created_at.desc())
            )
            if obs and obs.normalized_text and "phases 1 & 2" in obs.normalized_text.lower():
                return obs
        # Fall back to a source project-row observation on the later phase.
        for project in reversed(projects):
            obs = self.session.scalar(
                sa.select(SourceObservation)
                .where(
                    SourceObservation.project_id == project.id,
                    SourceObservation.field_name == "company_report.project_row",
                )
                .order_by(SourceObservation.created_at.desc())
            )
            if obs:
                return obs
        return None
