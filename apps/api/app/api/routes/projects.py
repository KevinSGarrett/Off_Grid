from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_policy, get_session
from app.api.serialization import jsonable
from app.models import (
    AssessmentFactor,
    OpportunityAssessment,
    ProductFitAssessment,
    Project,
    ProjectGroup,
    ProjectOrganization,
    Organization,
    ProjectSignal,
    QualityFlag,
    SourceEvidence,
    SourceObservation,
)
from app.scoring.qualification import QualificationService
from app.services.privacy import render_demo_value

router = APIRouter(tags=["projects"])


def _project_or_404(session: Session, project_id: UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(project_id)})
    return project


def _project_dict(project: Project) -> dict[str, object]:
    return {
        "id": str(project.id),
        "external_id": project.external_id,
        "canonical_name": project.canonical_name,
        "state": project.state.value,
        "stage": project.stage,
        "category": project.category,
        "city": project.city,
        "region": project.region,
        "country_code": project.country_code,
        "reported_value": str(project.reported_value) if project.reported_value is not None else None,
        "currency_code": project.currency_code,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "completion_date": project.completion_date.isoformat() if project.completion_date else None,
        "project_group_id": str(project.project_group_id) if project.project_group_id else None,
        "phase_label": project.phase_label,
        "is_synthetic": project.is_synthetic,
    }


@router.get("/projects")
def list_projects(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_synthetic: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    stmt = sa.select(Project).order_by(Project.created_at.desc()).offset(offset).limit(limit)
    if not include_synthetic:
        stmt = stmt.where(Project.is_synthetic.is_(False))
    rows = session.scalars(stmt).all()
    return {"items": [_project_dict(row) for row in rows], "count": len(rows), "limit": limit, "offset": offset}


@router.get("/projects/{project_id}")
def get_project(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    return _project_dict(_project_or_404(session, project_id))


@router.get("/projects/{project_id}/organizations")
def get_project_organizations(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    rows = session.execute(
        sa.select(ProjectOrganization, Organization)
        .join(Organization, ProjectOrganization.organization_id == Organization.id)
        .where(ProjectOrganization.project_id == project_id)
        .order_by(ProjectOrganization.role, Organization.canonical_name)
    ).all()
    group = session.get(ProjectGroup, project.project_group_id) if project.project_group_id else None
    siblings = []
    if group is not None:
        sibling_rows = session.scalars(
            sa.select(Project)
            .where(Project.project_group_id == group.id)
            .order_by(Project.phase_start_number.asc().nullslast(), Project.canonical_name)
        ).all()
        siblings = [
            {
                "id": str(row.id),
                "external_id": row.external_id,
                "canonical_name": row.canonical_name,
                "phase_label": row.phase_label,
                "stage": row.stage,
                "reported_value": str(row.reported_value) if row.reported_value is not None else None,
            }
            for row in sibling_rows
        ]
    return {
        "project_id": str(project_id),
        "project_group": None
        if group is None
        else {
            "id": str(group.id),
            "canonical_name": group.canonical_name,
            "group_type": group.group_type,
            "description": group.description,
            "projects": siblings,
        },
        "items": [
            {
                "relationship_id": str(relationship.id),
                "organization_id": str(organization.id),
                "canonical_name": organization.canonical_name,
                "organization_type": organization.organization_type,
                "role": relationship.role,
                "verification_state": relationship.verification_state.value,
            }
            for relationship, organization in rows
        ],
        "count": len(rows),
    }


@router.get("/projects/{project_id}/signals")
def get_project_signals(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    _project_or_404(session, project_id)
    rows = session.scalars(sa.select(ProjectSignal).where(ProjectSignal.project_id == project_id).order_by(ProjectSignal.signal_key)).all()
    return {
        "project_id": str(project_id),
        "items": [
            {
                "id": str(row.id),
                "key": row.signal_key,
                "value": row.signal_value,
                "classification": row.classification.value,
                "confidence_score": str(row.confidence_score) if row.confidence_score is not None else None,
                "source_observation_id": str(row.source_observation_id) if row.source_observation_id else None,
                "explanation": row.explanation,
            }
            for row in rows
        ],
    }


@router.get("/projects/{project_id}/evidence")
def get_project_evidence(
    project_id: UUID,
    session: Session = Depends(get_session),
    policy=Depends(get_runtime_policy),
) -> dict[str, object]:
    _project_or_404(session, project_id)
    rows = session.execute(
        sa.select(SourceEvidence, SourceObservation)
        .join(SourceObservation, SourceEvidence.observation_id == SourceObservation.id)
        .where(SourceObservation.project_id == project_id, SourceEvidence.is_permitted_for_decision.is_(True))
        .order_by(SourceEvidence.page_number, SourceObservation.field_name, SourceEvidence.id)
    ).all()
    items = []
    for evidence, observation in rows:
        excerpt = render_demo_value(
            evidence.excerpt,
            policy=evidence.demo_masking_policy,
            demo_mode=policy.demo_mode,
        )
        items.append(
            {
                "evidence_id": f"src:{evidence.id}",
                "observation_id": str(observation.id),
                "field_name": observation.field_name,
                "classification": evidence.classification.value,
                "page_number": evidence.page_number,
                "section_name": evidence.section_name,
                "excerpt": excerpt,
                "confidence_state": observation.confidence_state.value,
                "validation_state": observation.validation_state.value,
                "scoring_treatment": observation.scoring_treatment.value,
                "decision_eligible": observation.decision_eligible,
            }
        )
    return {"project_id": str(project_id), "items": items, "count": len(items), "demo_mode": policy.demo_mode}


@router.get("/projects/{project_id}/quality")
def get_project_quality(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    _project_or_404(session, project_id)
    rows = session.scalars(
        sa.select(QualityFlag).where(QualityFlag.project_id == project_id).order_by(QualityFlag.severity.desc(), QualityFlag.created_at)
    ).all()
    return {
        "project_id": str(project_id),
        "items": [
            {
                "id": str(row.id),
                "rule_code": row.rule_code,
                "severity": row.severity.value,
                "state": row.state.value,
                "title": row.title,
                "detail": row.detail,
                "decision_impact": row.decision_impact,
                "blocks_progression": row.blocks_progression,
            }
            for row in rows
        ],
    }


@router.get("/projects/{project_id}/assessment")
def get_project_assessment(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    _project_or_404(session, project_id)
    assessment = session.scalar(
        sa.select(OpportunityAssessment).where(OpportunityAssessment.project_id == project_id, OpportunityAssessment.is_current.is_(True))
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND", "message": "Run qualification first."})
    factors = session.scalars(sa.select(AssessmentFactor).where(AssessmentFactor.assessment_id == assessment.id).order_by(AssessmentFactor.factor_key)).all()
    products = session.scalars(sa.select(ProductFitAssessment).where(ProductFitAssessment.opportunity_assessment_id == assessment.id).order_by(ProductFitAssessment.product_code)).all()
    return {
        "project_id": str(project_id),
        "assessment": {
            "id": str(assessment.id),
            "commercial_fit_score": str(assessment.commercial_fit_score),
            "data_confidence_score": str(assessment.data_confidence_score),
            "disposition": assessment.disposition,
            "confidence_state": assessment.confidence_state.value,
            "computed_at": assessment.computed_at.isoformat(),
        },
        "factors": [
            {
                "key": row.factor_key,
                "label": row.label,
                "weight": str(row.weight),
                "raw_points": str(row.raw_points),
                "adjusted_points": str(row.adjusted_points),
                "cap_points": str(row.cap_points) if row.cap_points is not None else None,
                "classification": row.evidence_classification.value,
                "explanation": row.explanation,
            }
            for row in factors
        ],
        "product_fits": [
            {
                "product_code": row.product_code,
                "fit_score": str(row.fit_score),
                "fit_band": row.fit_band,
                "classification": row.classification.value,
                "confidence_state": row.confidence_state.value,
                "explanation": row.explanation,
                "missing_evidence": row.missing_evidence,
            }
            for row in products
        ],
    }


@router.post("/projects/{project_id}/sensitivity")
def run_project_sensitivity(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    _project_or_404(session, project_id)
    result = QualificationService(session).evaluate(project_id, persist=False)
    return {
        "project_id": str(project_id),
        "baseline": {
            "commercial_fit_score": str(result.commercial_fit_score),
            "disposition": result.disposition,
        },
        "counterfactuals": jsonable(result.counterfactuals),
        "what_would_change_my_mind": jsonable(result.what_would_change_my_mind),
        "decision_changing_unknowns": jsonable(result.decision_changing_unknowns),
        "persisted": False,
    }
