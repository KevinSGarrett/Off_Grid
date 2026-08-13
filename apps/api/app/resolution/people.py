from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.domain.states import ContactPointType, VerificationState
from app.ingestion.normalization import is_generic_email, normalized_name
from app.models import (
    Person,
    PersonAlias,
    PersonContactPoint,
    Project,
    ProjectPerson,
    SourceObservation,
)
from app.resolution.types import ContactRecurrenceSignal, DuplicatePersonCandidate


def _points(session: Session, person_id: UUID, contact_type: ContactPointType) -> list[PersonContactPoint]:
    return list(
        session.scalars(
            sa.select(PersonContactPoint).where(
                PersonContactPoint.person_id == person_id,
                PersonContactPoint.contact_type == contact_type,
            )
        ).all()
    )


def _individual_emails(session: Session, person_id: UUID) -> set[str]:
    return {
        row.normalized_value
        for row in _points(session, person_id, ContactPointType.EMAIL)
        if not row.is_generic and not is_generic_email(row.normalized_value)
    }


def _generic_emails(session: Session, person_id: UUID) -> set[str]:
    return {
        row.normalized_value
        for row in _points(session, person_id, ContactPointType.EMAIL)
        if row.is_generic or is_generic_email(row.normalized_value)
    }


def _phones(session: Session, person_id: UUID) -> set[str]:
    return {row.normalized_value for row in _points(session, person_id, ContactPointType.PHONE)}


def _canonical_quality(session: Session, person: Person) -> tuple[int, int, int, str]:
    individual = len(_individual_emails(session, person.id))
    active = 1 if person.status == "ACTIVE" else 0
    contact_count = len(_points(session, person.id, ContactPointType.EMAIL)) + len(
        _points(session, person.id, ContactPointType.PHONE)
    )
    # lexical id component keeps selection deterministic across equal-quality source rows.
    return (individual, active, contact_count, str(person.id))


class PersonResolutionService:
    """Conservative source-person resolution for account intelligence.

    Source-identity resolution does not verify employment/project authority externally and never marks rental authority.
    It chooses a canonical representative only for source-level recurrence/linking and leaves fuzzy
    duplicate source records visible for review rather than deleting them.
    """

    def __init__(self, session: Session):
        self.session = session

    def duplicate_candidates(self, organization_id: UUID) -> tuple[DuplicatePersonCandidate, ...]:
        people = list(
            self.session.scalars(
                sa.select(Person).where(Person.current_organization_id == organization_id).order_by(Person.display_name)
            ).all()
        )
        parent: dict[UUID, UUID] = {person.id: person.id for person in people}
        by_id = {person.id: person for person in people}
        edge_decisions: dict[frozenset[UUID], dict] = {}

        def find(pid: UUID) -> UUID:
            while parent[pid] != pid:
                parent[pid] = parent[parent[pid]]
                pid = parent[pid]
            return pid

        def union(a: UUID, b: UUID) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i, left in enumerate(people):
            for right in people[i + 1 :]:
                decision = self._compare(left, right)
                if decision is None:
                    continue
                edge_decisions[frozenset((left.id, right.id))] = decision
                union(left.id, right.id)

        components: dict[UUID, list[Person]] = defaultdict(list)
        for person in people:
            components[find(person.id)].append(person)

        results: list[DuplicatePersonCandidate] = []
        for component in components.values():
            if len(component) < 2:
                continue
            canonical = max(component, key=lambda p: _canonical_quality(self.session, p))
            for duplicate in component:
                if duplicate.id == canonical.id:
                    continue
                decision = edge_decisions.get(frozenset((canonical.id, duplicate.id)))
                if decision is None:
                    # Transitive duplicate candidate: preserve review semantics rather than asserting identity.
                    name_similarity = fuzz.ratio(canonical.normalized_name, duplicate.normalized_name)
                    decision = {
                        "decision": "REVIEW_DUPLICATE",
                        "match_method": "TRANSITIVE_DUPLICATE_CLUSTER",
                        "name_similarity": Decimal(str(round(name_similarity / 100, 4))),
                        "same_individual_email": bool(_individual_emails(self.session, canonical.id) & _individual_emails(self.session, duplicate.id)),
                        "same_phone": bool(_phones(self.session, canonical.id) & _phones(self.session, duplicate.id)),
                        "shared_generic_email_only": bool(_generic_emails(self.session, canonical.id) & _generic_emails(self.session, duplicate.id)),
                        "review_required": True,
                        "rationale": "This source record joins a duplicate component transitively; preserve it for review rather than silently merging it.",
                    }
                results.append(
                    DuplicatePersonCandidate(
                        canonical_person_id=canonical.id,
                        duplicate_person_id=duplicate.id,
                        canonical_name=canonical.display_name,
                        duplicate_name=duplicate.display_name,
                        **decision,
                    )
                )
        return tuple(sorted(results, key=lambda x: (x.canonical_name.lower(), x.duplicate_name.lower(), str(x.duplicate_person_id))))

    def apply_source_canonicalization(
        self,
        organization_id: UUID,
        duplicates: tuple[DuplicatePersonCandidate, ...] | None = None,
    ) -> dict[UUID, UUID]:
        duplicates = duplicates or self.duplicate_candidates(organization_id)
        canonical_map: dict[UUID, UUID] = {}
        for row in duplicates:
            # Do not delete or reassign source observations. Preserve source-record lineage.
            canonical_map[row.duplicate_person_id] = row.canonical_person_id
            canonical = self.session.get(Person, row.canonical_person_id)
            duplicate = self.session.get(Person, row.duplicate_person_id)
            if canonical is None or duplicate is None:
                continue
            self._ensure_alias(canonical, duplicate.display_name)
            if row.decision == "STRONG_DUPLICATE":
                duplicate.status = "DUPLICATE_SOURCE_RECORD"
            else:
                duplicate.status = "REVIEW_DUPLICATE_CANDIDATE"
        self.session.flush()
        return canonical_map

    def link_project_contacts(
        self,
        organization_id: UUID,
        *,
        canonical_map: dict[UUID, UUID] | None = None,
    ) -> int:
        canonical_map = canonical_map or {}
        people = list(
            self.session.scalars(sa.select(Person).where(Person.current_organization_id == organization_id)).all()
        )
        by_norm: dict[str, list[Person]] = defaultdict(list)
        for person in people:
            by_norm[person.normalized_name].append(person)
        aliases = self.session.execute(
            sa.select(PersonAlias.normalized_alias, PersonAlias.person_id)
            .join(Person, PersonAlias.person_id == Person.id)
            .where(Person.current_organization_id == organization_id)
        ).all()
        alias_to_person: dict[str, UUID] = {alias: pid for alias, pid in aliases}

        observations = list(
            self.session.scalars(
                sa.select(SourceObservation).where(
                    SourceObservation.organization_id == organization_id,
                    SourceObservation.field_name == "company_report.project.contact",
                    SourceObservation.project_id.is_not(None),
                )
            ).all()
        )
        created = 0
        for obs in observations:
            raw_name = (obs.normalized_text or obs.raw_value or "").strip()
            if not raw_name:
                continue
            norm = normalized_name(raw_name)
            person_id = alias_to_person.get(norm)
            if person_id is None:
                candidates = by_norm.get(norm, [])
                if candidates:
                    chosen = max(candidates, key=lambda p: _canonical_quality(self.session, p))
                    person_id = canonical_map.get(chosen.id, chosen.id)
                else:
                    fuzzy = self._best_fuzzy_person(norm, people)
                    if fuzzy is None:
                        continue
                    person_id = canonical_map.get(fuzzy.id, fuzzy.id)
            role_obs = self.session.scalar(
                sa.select(SourceObservation)
                .where(
                    SourceObservation.document_id == obs.document_id,
                    SourceObservation.project_id == obs.project_id,
                    SourceObservation.organization_id == organization_id,
                    SourceObservation.field_name == "company_report.project.role",
                )
                .order_by(SourceObservation.created_at.desc())
            )
            role = role_obs.normalized_text if role_obs else "SOURCE_PROJECT_CONTACT"
            existing = self.session.scalar(
                sa.select(ProjectPerson).where(
                    ProjectPerson.project_id == obs.project_id,
                    ProjectPerson.person_id == person_id,
                    ProjectPerson.role == role,
                )
            )
            if existing is None:
                self.session.add(
                    ProjectPerson(
                        project_id=obs.project_id,
                        person_id=person_id,
                        organization_id=organization_id,
                        role=role,
                        association_state=VerificationState.SUPPORTED,
                        source_observation_id=obs.id,
                    )
                )
                created += 1
        self.session.flush()
        return created

    def recurrence_signals(self, organization_id: UUID) -> tuple[ContactRecurrenceSignal, ...]:
        rows = self.session.execute(
            sa.select(ProjectPerson, Person, Project)
            .join(Person, ProjectPerson.person_id == Person.id)
            .join(Project, ProjectPerson.project_id == Project.id)
            .where(ProjectPerson.organization_id == organization_id)
        ).all()
        grouped: dict[UUID, dict] = {}
        for link, person, project in rows:
            slot = grouped.setdefault(
                person.id,
                {"person": person, "projects": {}, "roles": set(), "source_count": 0},
            )
            slot["projects"][project.id] = project.canonical_name
            if link.role:
                slot["roles"].add(link.role)
            slot["source_count"] += 1
        results: list[ContactRecurrenceSignal] = []
        for slot in grouped.values():
            count = len(slot["projects"])
            if count < 2:
                continue
            band = "HIGH" if count >= 4 else "MEDIUM" if count >= 2 else "LOW"
            person = slot["person"]
            ordered_projects = sorted(slot["projects"].items(), key=lambda x: x[1].lower())
            results.append(
                ContactRecurrenceSignal(
                    person_id=person.id,
                    person_name=person.display_name,
                    unique_project_count=count,
                    source_association_count=slot["source_count"],
                    project_ids=tuple(pid for pid, _ in ordered_projects),
                    project_names=tuple(name for _, name in ordered_projects),
                    roles=tuple(sorted(slot["roles"])),
                    recurrence_band=band,
                    rental_authority_implied=False,
                )
            )
        return tuple(sorted(results, key=lambda x: (-x.unique_project_count, x.person_name.lower())))

    def _best_fuzzy_person(self, normalized_source_name: str, people: list[Person]) -> Person | None:
        if not people:
            return None
        scored = sorted(
            ((fuzz.ratio(normalized_source_name, p.normalized_name), p) for p in people),
            key=lambda x: (x[0], _canonical_quality(self.session, x[1])),
            reverse=True,
        )
        if scored[0][0] < 90:
            return None
        # Fuzzy linkage is only accepted here when a same-organization source contact row exists;
        # it creates a SUPPORTED project association, not a verified identity/authority claim.
        return scored[0][1]

    def _compare(self, left: Person, right: Person) -> dict | None:
        left_individual = _individual_emails(self.session, left.id)
        right_individual = _individual_emails(self.session, right.id)
        same_individual = bool(left_individual & right_individual)
        left_generic = _generic_emails(self.session, left.id)
        right_generic = _generic_emails(self.session, right.id)
        shared_generic = bool(left_generic & right_generic) and not same_individual
        same_phone = bool(_phones(self.session, left.id) & _phones(self.session, right.id))
        name_similarity = fuzz.ratio(left.normalized_name, right.normalized_name)
        exact_name = left.normalized_name == right.normalized_name

        if same_individual:
            return {
                "decision": "STRONG_DUPLICATE",
                "match_method": "EXACT_INDIVIDUAL_EMAIL",
                "name_similarity": Decimal(str(round(name_similarity / 100, 4))),
                "same_individual_email": True,
                "same_phone": same_phone,
                "shared_generic_email_only": shared_generic,
                "review_required": False,
                "rationale": "Exact non-generic email identity is shared; source rows are retained but one representative is used for recurrence/linking.",
            }
        if exact_name and same_phone:
            return {
                "decision": "REVIEW_DUPLICATE",
                "match_method": "EXACT_NAME_PLUS_SHARED_PHONE",
                "name_similarity": Decimal("1.0000"),
                "same_individual_email": False,
                "same_phone": True,
                "shared_generic_email_only": shared_generic,
                "review_required": True,
                "rationale": "Exact normalized name and phone match, but the source may contain different/generic email evidence; review before destructive merge.",
            }
        if name_similarity >= 90 and same_phone:
            return {
                "decision": "REVIEW_DUPLICATE",
                "match_method": "FUZZY_NAME_PLUS_SHARED_PHONE",
                "name_similarity": Decimal(str(round(name_similarity / 100, 4))),
                "same_individual_email": False,
                "same_phone": True,
                "shared_generic_email_only": shared_generic,
                "review_required": True,
                "rationale": "High name similarity and shared phone indicate a probable malformed/duplicate source row; fuzzy evidence cannot silently merge people.",
            }
        return None

    def _choose_representative(self, left: Person, right: Person) -> tuple[Person, Person]:
        if _canonical_quality(self.session, left) >= _canonical_quality(self.session, right):
            return left, right
        return right, left

    def _ensure_alias(self, person: Person, alias: str) -> None:
        norm = normalized_name(alias)
        existing = self.session.scalar(
            sa.select(PersonAlias).where(
                PersonAlias.person_id == person.id,
                PersonAlias.normalized_alias == norm,
            )
        )
        # Session autoflush is intentionally disabled. Multiple duplicate edges can therefore
        # request the same alias before the database query can see the pending insert. Check the
        # identity map/new collection as well so canonicalization remains idempotent in file-backed
        # and long-lived API sessions.
        if existing is None:
            existing = next(
                (
                    row
                    for row in self.session.new
                    if isinstance(row, PersonAlias)
                    and row.person_id == person.id
                    and row.normalized_alias == norm
                ),
                None,
            )
        if existing is None:
            self.session.add(
                PersonAlias(
                    person_id=person.id,
                    alias=alias,
                    normalized_alias=norm,
                )
            )
