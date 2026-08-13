from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.accounts.service import AccountIntelligenceService
from app.api.dependencies import get_runtime_policy, get_session
from app.api.serialization import jsonable
from app.models import (
    ContactAssessment,
    ContactCandidate,
    Organization,
    OrganizationAddress,
    OrganizationAlias,
    OrganizationDomain,
    Person,
    PersonAlias,
    PersonContactPoint,
    Project,
    ProjectOrganization,
    ProjectPerson,
    QualityFlag,
    SourceDocument,
    SourceObservation,
)
from app.services.privacy import render_demo_value

router = APIRouter(tags=["organizations"])


def _org_or_404(session: Session, organization_id: UUID) -> Organization:
    row = session.get(Organization, organization_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ORGANIZATION_NOT_FOUND", "organization_id": str(organization_id)},
        )
    return row


@router.get("/organizations/{organization_id}")
def get_organization(
    organization_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    org = _org_or_404(session, organization_id)
    aliases = session.scalars(
        sa.select(OrganizationAlias)
        .where(OrganizationAlias.organization_id == org.id)
        .order_by(OrganizationAlias.alias)
    ).all()
    domains = session.scalars(
        sa.select(OrganizationDomain)
        .where(OrganizationDomain.organization_id == org.id)
        .order_by(OrganizationDomain.normalized_domain)
    ).all()
    addresses = session.scalars(
        sa.select(OrganizationAddress)
        .where(OrganizationAddress.organization_id == org.id)
        .order_by(OrganizationAddress.created_at)
    ).all()
    return {
        "id": str(org.id),
        "canonical_name": org.canonical_name,
        "canonical_key": org.canonical_key,
        "organization_type": org.organization_type,
        "status": org.status,
        "aliases": [{"alias": row.alias, "alias_type": row.alias_type} for row in aliases],
        "domains": [
            {
                "domain": row.domain,
                "relationship_state": row.relationship_state.value,
                "is_primary": row.is_primary,
            }
            for row in domains
        ],
        "addresses": [
            {
                "address_type": row.address_type,
                "line1": row.line1,
                "line2": row.line2,
                "city": row.city,
                "region": row.region,
                "postal_code": row.postal_code,
                "country_code": row.country_code,
            }
            for row in addresses
        ],
    }


@router.get("/organizations/{organization_id}/projects")
def get_organization_projects(
    organization_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    _org_or_404(session, organization_id)
    rows = session.execute(
        sa.select(ProjectOrganization, Project)
        .join(Project, ProjectOrganization.project_id == Project.id)
        .where(ProjectOrganization.organization_id == organization_id)
        .order_by(Project.created_at.desc())
    ).all()
    return {
        "organization_id": str(organization_id),
        "items": [
            {
                "project_id": str(project.id),
                "external_id": project.external_id,
                "canonical_name": project.canonical_name,
                "role": relationship.role,
                "verification_state": relationship.verification_state.value,
                "stage": project.stage,
                "state": project.state.value,
            }
            for relationship, project in rows
        ],
    }


@router.get("/organizations/{organization_id}/contacts")
def get_organization_contacts(
    organization_id: UUID,
    session: Session = Depends(get_session),
    policy=Depends(get_runtime_policy),
) -> dict[str, object]:
    _org_or_404(session, organization_id)
    person_ids = set(
        session.scalars(
            sa.select(Person.id).where(Person.current_organization_id == organization_id)
        ).all()
    )
    person_ids.update(
        session.scalars(
            sa.select(ProjectPerson.person_id).where(
                ProjectPerson.organization_id == organization_id
            )
        ).all()
    )
    if not person_ids:
        return {
            "organization_id": str(organization_id),
            "items": [],
            "count": 0,
            "demo_mode": policy.demo_mode,
        }
    people = session.scalars(
        sa.select(Person).where(Person.id.in_(person_ids)).order_by(Person.display_name)
    ).all()
    points = session.scalars(
        sa.select(PersonContactPoint)
        .where(PersonContactPoint.person_id.in_(person_ids))
        .order_by(PersonContactPoint.person_id, PersonContactPoint.contact_type)
    ).all()
    by_person: dict[UUID, list[dict[str, object]]] = {}
    for point in points:
        by_person.setdefault(point.person_id, []).append(
            {
                "type": point.contact_type.value,
                "value": render_demo_value(
                    point.value,
                    policy=point.demo_masking_policy,
                    contact_type=point.contact_type,
                    demo_mode=policy.demo_mode,
                ),
                "verification_state": point.verification_state.value,
                "is_generic": point.is_generic,
                "is_primary": point.is_primary,
            }
        )
    return {
        "organization_id": str(organization_id),
        "items": [
            {
                "person_id": str(person.id),
                "display_name": person.display_name,
                "employment_state": person.employment_state.value,
                "status": person.status,
                "contact_points": by_person.get(person.id, []),
            }
            for person in people
        ],
        "count": len(people),
        "demo_mode": policy.demo_mode,
    }


@router.get("/organizations/{organization_id}/intelligence")
def get_organization_intelligence(
    organization_id: UUID,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    org = _org_or_404(session, organization_id)
    result = jsonable(AccountIntelligenceService(session).analyze(organization_id))
    source_contact_rows = (
        session.scalar(
            sa.select(sa.func.count(SourceObservation.id)).where(
                SourceObservation.organization_id == organization_id,
                SourceObservation.field_name == "person.source_contact_row",
            )
        )
        or 0
    )
    source_contact_people = (
        session.scalar(
            sa.select(sa.func.count(sa.distinct(SourceObservation.person_id))).where(
                SourceObservation.organization_id == organization_id,
                SourceObservation.field_name == "person.source_contact_row",
                SourceObservation.person_id.is_not(None),
            )
        )
        or 0
    )
    source_person_ids = list(
        session.scalars(
            sa.select(SourceObservation.person_id).where(
                SourceObservation.organization_id == organization_id,
                SourceObservation.field_name == "person.source_contact_row",
                SourceObservation.person_id.is_not(None),
            )
        ).all()
    )
    generic_inboxes = (
        session.scalar(
            sa.select(sa.func.count(PersonContactPoint.id)).where(
                PersonContactPoint.person_id.in_(source_person_ids),
                PersonContactPoint.is_generic.is_(True),
            )
        )
        or 0
    )
    inactive_contacts = (
        session.scalar(
            sa.select(sa.func.count(Person.id)).where(
                Person.id.in_(source_person_ids),
                sa.func.upper(Person.status) == "INACTIVE",
            )
        )
        or 0
    )
    known_domains = (
        session.scalar(
            sa.select(sa.func.count(OrganizationDomain.id)).where(
                OrganizationDomain.organization_id == organization_id
            )
        )
        or 0
    )
    report = session.scalar(
        sa.select(SourceDocument)
        .join(SourceObservation, SourceObservation.document_id == SourceDocument.id)
        .where(
            SourceDocument.report_type == "COMPANY",
            SourceObservation.organization_id == organization_id,
        )
        .order_by(SourceDocument.report_date.desc())
    )
    source_last_update = session.scalar(
        sa.select(SourceObservation.normalized_datetime)
        .where(
            SourceObservation.organization_id == organization_id,
            SourceObservation.field_name == "organization.source_last_update",
        )
        .order_by(SourceObservation.normalized_datetime.desc())
    )
    result.update(
        {
            "constructconnect_company_id": (
                org.canonical_key.rsplit(":", 1)[-1]
                if org.canonical_key.startswith("constructconnect:company:")
                else None
            ),
            "source_contact_rows": int(source_contact_rows),
            "canonical_source_contacts": int(source_contact_people),
            "generic_inbox_records": int(generic_inboxes),
            "inactive_source_contacts": int(inactive_contacts),
            "known_domain_count": int(known_domains),
            "report_date": report.report_date.isoformat()
            if report and report.report_date
            else None,
            "source_company_last_update": (
                source_last_update.isoformat() if source_last_update else None
            ),
            "source_company_last_update_note": (
                "Company Last Update is source metadata and differs from the report generation date."
                if source_last_update
                else "Company Last Update is unavailable in the current persisted seed; no value is inferred."
            ),
        }
    )
    return result


@router.get("/organizations/{organization_id}/source-contacts")
def get_organization_source_contacts(
    organization_id: UUID,
    comparison_project_id: UUID | None = Query(None),
    session: Session = Depends(get_session),
    policy=Depends(get_runtime_policy),
) -> dict[str, object]:
    _org_or_404(session, organization_id)
    source_observations = list(
        session.scalars(
            sa.select(SourceObservation)
            .where(
                SourceObservation.organization_id == organization_id,
                SourceObservation.field_name == "person.source_contact_row",
                SourceObservation.person_id.is_not(None),
            )
            .order_by(SourceObservation.created_at, SourceObservation.id)
        ).all()
    )
    source_person_ids = {row.person_id for row in source_observations if row.person_id is not None}
    people = {
        person.id: person
        for person in session.scalars(
            sa.select(Person).where(Person.id.in_(source_person_ids))
        ).all()
    }
    aliases: dict[UUID, list[str]] = {}
    for alias in session.scalars(
        sa.select(PersonAlias).where(PersonAlias.person_id.in_(source_person_ids))
    ).all():
        aliases.setdefault(alias.person_id, []).append(alias.alias)
    points: dict[UUID, list[dict[str, object]]] = {}
    domains: dict[UUID, set[str]] = {}
    for point in session.scalars(
        sa.select(PersonContactPoint)
        .where(PersonContactPoint.person_id.in_(source_person_ids))
        .order_by(PersonContactPoint.person_id, PersonContactPoint.contact_type)
    ).all():
        points.setdefault(point.person_id, []).append(
            {
                "type": point.contact_type.value,
                "value": render_demo_value(
                    point.value,
                    policy=point.demo_masking_policy,
                    contact_type=point.contact_type,
                    demo_mode=policy.demo_mode,
                ),
                "verification_state": point.verification_state.value,
                "is_generic": point.is_generic,
                "is_primary": point.is_primary,
            }
        )
        if "@" in point.normalized_value:
            domains.setdefault(point.person_id, set()).add(
                point.normalized_value.rsplit("@", 1)[-1]
            )
    flags: dict[UUID, list[dict[str, object]]] = {}
    for flag in session.scalars(
        sa.select(QualityFlag)
        .where(QualityFlag.person_id.in_(source_person_ids))
        .order_by(QualityFlag.rule_code)
    ).all():
        if flag.person_id is not None:
            flags.setdefault(flag.person_id, []).append(
                {
                    "rule_code": flag.rule_code,
                    "severity": flag.severity.value,
                    "state": flag.state.value,
                    "title": flag.title,
                }
            )
    project_links: dict[UUID, int] = {
        person_id: int(count)
        for person_id, count in session.execute(
            sa.select(ProjectPerson.person_id, sa.func.count(ProjectPerson.id))
            .where(ProjectPerson.person_id.in_(source_person_ids))
            .group_by(ProjectPerson.person_id)
        ).all()
    }
    comparison_project = session.get(Project, comparison_project_id) if comparison_project_id else None
    comparison_project_links: set[UUID] = set()
    if comparison_project is not None:
        comparison_project_links = set(
            session.scalars(
                sa.select(ProjectPerson.person_id).where(
                    ProjectPerson.project_id == comparison_project.id,
                    ProjectPerson.person_id.in_(source_person_ids),
                )
            ).all()
        )
    candidate_stmt = sa.select(ContactCandidate).where(ContactCandidate.is_current.is_(True))
    candidate_stmt = (
        candidate_stmt.where(ContactCandidate.project_id == comparison_project.id)
        if comparison_project is not None
        else candidate_stmt.where(sa.false())
    )
    candidates = list(session.scalars(candidate_stmt).all())
    candidate_by_person = {candidate.person_id: candidate for candidate in candidates}
    candidate_ids = [candidate.id for candidate in candidates]
    authority_states = list(
        session.scalars(
            sa.select(ContactAssessment.rental_authority_state).where(
                ContactAssessment.candidate_id.in_(candidate_ids),
                ContactAssessment.is_current.is_(True),
            )
        ).all()
    )
    occurrences: dict[UUID, int] = {}
    for observation in source_observations:
        if observation.person_id is not None:
            occurrences[observation.person_id] = occurrences.get(observation.person_id, 0) + 1
    items = []
    for person_id in sorted(source_person_ids, key=lambda value: people[value].display_name):
        person = people[person_id]
        candidate = candidate_by_person.get(person_id)
        person_points = points.get(person_id, [])
        quality = flags.get(person_id, [])
        rank_eligible = candidate is not None
        items.append(
            {
                "person_id": str(person.id),
                "display_name": person.display_name,
                "source_status": person.status,
                "employment_state": person.employment_state.value,
                "source_occurrence_count": occurrences.get(person.id, 0),
                "aliases": sorted(aliases.get(person.id, [])),
                "contact_points": person_points,
                "domains": sorted(domains.get(person.id, set())),
                "generic_inbox": any(bool(point["is_generic"]) for point in person_points),
                "identity_quality": "REVIEW" if quality else "RESOLVED_SOURCE_IDENTITY",
                "quality_findings": quality,
                "project_association_count": int(project_links.get(person.id, 0)),
                "selected_project_association": (
                    "SUPPORTED" if person.id in comparison_project_links else "UNKNOWN"
                ),
                "rank_eligible": rank_eligible,
                "rank_eligibility_reason": (
                    "Current selected-project candidate evidence is available."
                    if rank_eligible
                    else "No current selected-project candidate relationship; source-directory presence alone is not rank evidence."
                ),
                "investigation_status": candidate.state.value if candidate else "NOT_RANK_ELIGIBLE",
            }
        )
    top_candidate = min(candidates, key=lambda row: row.rank or 10_000) if candidates else None
    top_person = session.get(Person, top_candidate.person_id) if top_candidate else None
    return {
        "organization_id": str(organization_id),
        "items": items,
        "count": len(items),
        "source_row_count": len(source_observations),
        "demo_mode": policy.demo_mode,
        "funnel": {
            "source_directory_rows": len(source_observations),
            "canonical_source_identities": len(source_person_ids),
            "source_people_with_any_project_association": len(project_links),
            "project_research_candidates": len(candidates),
            "current_top_investigation_candidates": 1 if top_candidate else 0,
            "authority_verified": len(
                [state for state in authority_states if state.value == "VERIFIED"]
            ),
            "top_candidate": top_person.display_name if top_person else None,
            "sets_are_distinct": True,
        },
        "semantics": {
            "directory": "Source-directory records are evidence of supplied contact data, not proof of selected-project responsibility or rental authority.",
            "candidates": "Selected-project research candidates are a separate project-specific investigation set.",
        },
    }
