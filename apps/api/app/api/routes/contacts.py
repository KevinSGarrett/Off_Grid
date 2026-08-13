from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import RuntimePolicy, get_session, require_internal_mutation_allowed
from app.contact_resolution.verification import ContactVerificationService
from app.domain.states import IntegrationMode, VerificationState
from app.integrations.apollo import ApolloAdapter, ApolloRequestPreview
from app.models import (
    ContactAssessment,
    ContactCandidate,
    ExternalEvidence,
    Organization,
    OrganizationDomain,
    Person,
    Project,
    ProjectOrganization,
)

router = APIRouter(tags=["contacts"])


def _utc_iso(value: datetime) -> str:
    timestamp = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return timestamp.isoformat()


class VerificationRequest(BaseModel):
    dimension: str
    verification_type: str
    outcome: VerificationState
    verified_by: str = Field(min_length=1, max_length=160)
    note: str = Field(min_length=1, max_length=4000)
    verified_at: datetime | None = None
    source_evidence_id: UUID | None = None
    external_evidence_id: UUID | None = None


def _preview_payload(preview: ApolloRequestPreview) -> dict[str, object]:
    return {
        "mode": "PREVIEW",
        "method": preview.method,
        "endpoint": preview.endpoint,
        "params": preview.params,
        "credit_consuming": preview.credit_consuming,
        "external_request_executed": False,
        "note": preview.note,
    }


@router.get("/projects/{project_id}/apollo-preview")
def get_apollo_preview(
    project_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    """Build Apollo search/enrichment requests without making a network call."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(project_id)}
        )

    organization_row = session.execute(
        sa.select(ProjectOrganization, Organization)
        .join(Organization, Organization.id == ProjectOrganization.organization_id)
        .where(ProjectOrganization.project_id == project_id)
        .order_by(
            sa.case(
                (sa.func.lower(ProjectOrganization.role).like("%general contractor%"), 0), else_=1
            ),
            ProjectOrganization.created_at.asc(),
        )
    ).first()
    if organization_row is None:
        return {
            "project_id": str(project_id),
            "eligible": False,
            "reason": "A supported contractor/account relationship is required before Apollo search can be previewed.",
            "external_requests_executed": 0,
        }
    relationship, organization = organization_row
    domain_rows = session.scalars(
        sa.select(OrganizationDomain)
        .where(OrganizationDomain.organization_id == organization.id)
        .order_by(OrganizationDomain.is_primary.desc(), OrganizationDomain.normalized_domain.asc())
    ).all()
    domains = [row.normalized_domain for row in domain_rows]
    if not domains:
        return {
            "project_id": str(project_id),
            "eligible": False,
            "reason": "A supported organization domain is required before Apollo search can be previewed.",
            "organization": organization.canonical_name,
            "external_requests_executed": 0,
        }

    titles = [
        "Project Executive",
        "Project Manager",
        "Superintendent",
        "Equipment Manager",
        "Fleet Manager",
        "Procurement Manager",
        "Operations Manager",
    ]
    location = ", ".join(value for value in (project.city, project.region) if value)
    adapter = ApolloAdapter(mode=IntegrationMode.PREVIEW)
    search = adapter.preview_search(
        titles=titles,
        domains=domains,
        person_locations=[location] if location else None,
        per_page=25,
    )
    candidate_row = session.execute(
        sa.select(ContactCandidate, ContactAssessment, Person)
        .join(Person, Person.id == ContactCandidate.person_id)
        .outerjoin(
            ContactAssessment,
            sa.and_(
                ContactAssessment.candidate_id == ContactCandidate.id,
                ContactAssessment.is_current.is_(True),
            ),
        )
        .where(ContactCandidate.project_id == project_id, ContactCandidate.is_current.is_(True))
        .order_by(ContactCandidate.rank.asc().nullslast(), ContactCandidate.candidate_score.desc())
    ).first()
    enrichment: dict[str, object] | None = None
    if candidate_row is not None:
        candidate, assessment, person = candidate_row
        request = adapter.preview_enrichment(name=person.display_name, domain=domains[0])
        enrichment = {
            "candidate_id": str(candidate.id),
            "person_id": str(person.id),
            "display_name": person.display_name,
            "target_persona": candidate.target_persona,
            "request": _preview_payload(request),
            "before": {
                "employment": assessment.employment_state.value if assessment else "UNKNOWN",
                "project_association": assessment.project_association_state.value
                if assessment
                else "UNKNOWN",
                "role_relevance": assessment.role_relevance_state.value
                if assessment
                else "UNKNOWN",
                "rental_authority": assessment.rental_authority_state.value
                if assessment
                else "UNKNOWN",
            },
            "constraints": [
                "Enrichment may support employment, title, and business contact evidence.",
                "Enrichment cannot independently verify project association or rental authority.",
                "May consume Apollo credits in an authorized live mode.",
            ],
        }
    return {
        "project_id": str(project_id),
        "eligible": True,
        "project": project.canonical_name,
        "organization_id": str(organization.id),
        "organization": organization.canonical_name,
        "organization_role": relationship.role,
        "supported_domains": domains,
        "target_personas": titles,
        "location_filters": [location] if location else [],
        "purpose": "Identify people who may own or route temporary-lighting, mobile-power, or rental decisions; results remain unverified until independently assessed.",
        "search": _preview_payload(search),
        "enrichment": enrichment,
        "external_requests_executed": 0,
    }


@router.get("/projects/{project_id}/contact-candidates")
def get_contact_candidates(
    project_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(project_id)}
        )
    rows = session.execute(
        sa.select(ContactCandidate, ContactAssessment, Person)
        .join(Person, ContactCandidate.person_id == Person.id)
        .outerjoin(
            ContactAssessment,
            sa.and_(
                ContactAssessment.candidate_id == ContactCandidate.id,
                ContactAssessment.is_current.is_(True),
            ),
        )
        .where(ContactCandidate.project_id == project_id, ContactCandidate.is_current.is_(True))
        .order_by(ContactCandidate.rank.asc().nullslast(), ContactCandidate.candidate_score.desc())
    ).all()
    person_ids = [person.id for _, _, person in rows]
    evidence_origins: dict[UUID, set[str]] = {}
    for person_id, source_type in session.execute(
        sa.select(ExternalEvidence.person_id, ExternalEvidence.source_type).where(
            ExternalEvidence.person_id.in_(person_ids)
        )
    ).all():
        if person_id is not None:
            label = (
                "COMPANY_WEBSITE"
                if source_type.startswith("EMPLOYER_OFFICIAL")
                else "PROJECT_SPECIFIC_PUBLIC_RESEARCH"
            )
            evidence_origins.setdefault(person_id, set()).add(label)
    items = []
    for candidate, assessment, person in rows:
        items.append(
            {
                "candidate_id": str(candidate.id),
                "person_id": str(person.id),
                "organization_id": str(candidate.organization_id)
                if candidate.organization_id
                else None,
                "display_name": person.display_name,
                "state": candidate.state.value,
                "rank": candidate.rank,
                "candidate_score": str(candidate.candidate_score)
                if candidate.candidate_score is not None
                else None,
                "target_persona": candidate.target_persona,
                "rationale": candidate.rationale,
                "evidence_origins": sorted(
                    evidence_origins.get(person.id, {"PROJECT_SPECIFIC_PUBLIC_RESEARCH"})
                ),
                "verification": None
                if assessment is None
                else {
                    "employment": assessment.employment_state.value,
                    "project_association": assessment.project_association_state.value,
                    "role_relevance": assessment.role_relevance_state.value,
                    "rental_authority": assessment.rental_authority_state.value,
                    "assessed_at": _utc_iso(assessment.assessed_at),
                },
            }
        )
    return {"project_id": str(project_id), "items": items, "count": len(items)}


@router.post("/contacts/{contact_id}/verification")
def verify_contact(
    contact_id: UUID,
    payload: VerificationRequest,
    _policy: Annotated[RuntimePolicy, Depends(require_internal_mutation_allowed)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    try:
        event = ContactVerificationService(session).record(
            candidate_id=contact_id,
            dimension=payload.dimension,
            verification_type=payload.verification_type,
            outcome=payload.outcome,
            verified_by=payload.verified_by,
            note=payload.note,
            verified_at=payload.verified_at,
            source_evidence_id=payload.source_evidence_id,
            external_evidence_id=payload.external_evidence_id,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=422, detail={"code": "VERIFICATION_REJECTED", "message": str(exc)}
        ) from exc
    return {
        "status": "recorded",
        "event_id": str(event.id),
        "candidate_id": str(event.candidate_id) if event.candidate_id else None,
        "dimension": event.dimension,
        "verification_type": event.verification_type,
        "outcome": event.outcome.value,
        "verified_at": _utc_iso(event.verified_at),
    }
