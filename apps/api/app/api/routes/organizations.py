from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_policy, get_session
from app.models import (
    Organization,
    OrganizationAddress,
    OrganizationAlias,
    OrganizationDomain,
    Person,
    PersonContactPoint,
    Project,
    ProjectOrganization,
    ProjectPerson,
)
from app.services.privacy import render_demo_value

router = APIRouter(tags=["organizations"])


def _org_or_404(session: Session, organization_id: UUID) -> Organization:
    row = session.get(Organization, organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "ORGANIZATION_NOT_FOUND", "organization_id": str(organization_id)})
    return row


@router.get("/organizations/{organization_id}")
def get_organization(organization_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    org = _org_or_404(session, organization_id)
    aliases = session.scalars(sa.select(OrganizationAlias).where(OrganizationAlias.organization_id == org.id).order_by(OrganizationAlias.alias)).all()
    domains = session.scalars(sa.select(OrganizationDomain).where(OrganizationDomain.organization_id == org.id).order_by(OrganizationDomain.normalized_domain)).all()
    addresses = session.scalars(sa.select(OrganizationAddress).where(OrganizationAddress.organization_id == org.id).order_by(OrganizationAddress.created_at)).all()
    return {
        "id": str(org.id),
        "canonical_name": org.canonical_name,
        "canonical_key": org.canonical_key,
        "organization_type": org.organization_type,
        "status": org.status,
        "aliases": [{"alias": row.alias, "alias_type": row.alias_type} for row in aliases],
        "domains": [
            {"domain": row.domain, "relationship_state": row.relationship_state.value, "is_primary": row.is_primary}
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
def get_organization_projects(organization_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
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
    person_ids = set(session.scalars(sa.select(Person.id).where(Person.current_organization_id == organization_id)).all())
    person_ids.update(session.scalars(sa.select(ProjectPerson.person_id).where(ProjectPerson.organization_id == organization_id)).all())
    if not person_ids:
        return {"organization_id": str(organization_id), "items": [], "count": 0, "demo_mode": policy.demo_mode}
    people = session.scalars(sa.select(Person).where(Person.id.in_(person_ids)).order_by(Person.display_name)).all()
    points = session.scalars(sa.select(PersonContactPoint).where(PersonContactPoint.person_id.in_(person_ids)).order_by(PersonContactPoint.person_id, PersonContactPoint.contact_type)).all()
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
