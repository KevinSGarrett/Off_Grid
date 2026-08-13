from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_policy, get_session
from app.api.serialization import jsonable
from app.domain.states import QualityFlagState, QualitySeverity
from app.models import (
    AssessmentFactor,
    OpportunityAssessment,
    Organization,
    Project,
    ProjectGroup,
    ProjectOrganization,
    ProjectSignal,
    QualityFlag,
    SourceEvidence,
    SourceDocument,
    SourceObservation,
)
from app.scoring.qualification import QualificationService
from app.services.privacy import render_demo_value
from app.services.batch_triage import (
    AssessmentCoverage,
    BatchProjectTriageService,
    derive_project_coverage,
)

router = APIRouter(tags=["projects"])

PORTFOLIO_SOURCE_FIELDS = {
    "company_report.project.name",
    "company_report.project.section",
    "company_report.project.role",
    "company_report.project.stage",
    "company_report.project.value",
    "company_report.project.bid_date",
    "company_report.project.contact",
}


class BatchTriageRequest(BaseModel):
    project_ids: list[UUID] = Field(min_length=1, max_length=500)


QUALITY_WARNING_ACTIONS = {
    "VIEWED_NOT_TRACKED": "Confirm whether this project should be added to active tracking and assign an owner.",
    "MISSING_PROJECT_GC_CONTACT": "Identify and verify project leadership and equipment responsibility.",
    "PROJECT_VALUE_UNCERTAINTY": "Retain the value as source-reported context; validate it only if phase value becomes commercially necessary.",
    "FUTURE_ACTUAL_DATE": "Verify current phase and start timing using a newer project-specific source.",
}


def quality_warning_action(rule_code: str) -> str:
    return QUALITY_WARNING_ACTIONS.get(
        rule_code,
        "Review the cited evidence, record the disposition, and assign an owner if follow-up is required.",
    )


def _project_or_404(session: Session, project_id: UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=404, detail={"code": "PROJECT_NOT_FOUND", "project_id": str(project_id)}
        )
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
        "reported_value": str(project.reported_value)
        if project.reported_value is not None
        else None,
        "currency_code": project.currency_code,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "completion_date": project.completion_date.isoformat() if project.completion_date else None,
        "project_group_id": str(project.project_group_id) if project.project_group_id else None,
        "phase_label": project.phase_label,
        "is_synthetic": project.is_synthetic,
    }


def _observation_has_value(observation: SourceObservation) -> bool:
    if any(
        value is not None
        for value in (
            observation.normalized_integer,
            observation.normalized_decimal,
            observation.normalized_boolean,
            observation.normalized_date,
            observation.normalized_datetime,
        )
    ):
        return True
    text = (observation.normalized_text or "").strip().upper()
    return bool(text and text not in {"N/A", "NA", "NONE", "UNKNOWN", "NOT AVAILABLE"})


@router.get("/portfolio/projects")
def get_project_portfolio(session: Session = Depends(get_session)) -> dict[str, object]:
    """Return the resolved source population without fabricating thin-record scores."""
    projects = list(
        session.scalars(
            sa.select(Project)
            .where(Project.is_synthetic.is_(False))
            .order_by(Project.canonical_name)
        ).all()
    )
    project_ids = [project.id for project in projects]
    coverage_by_project = derive_project_coverage(session, project_ids)
    source_documents = list(
        session.scalars(
            sa.select(SourceDocument).where(SourceDocument.is_synthetic.is_(False))
        ).all()
    )
    documents_by_id = {document.id: document for document in source_documents}
    observations = list(
        session.scalars(
            sa.select(SourceObservation).where(
                SourceObservation.project_id.in_(project_ids),
                SourceObservation.field_name.in_(PORTFOLIO_SOURCE_FIELDS),
            )
        ).all()
    )
    by_project: dict[UUID, list[SourceObservation]] = {}
    for observation in observations:
        if observation.project_id is not None:
            by_project.setdefault(observation.project_id, []).append(observation)

    current_assessments = {
        assessment.project_id: assessment
        for assessment in session.scalars(
            sa.select(OpportunityAssessment).where(
                OpportunityAssessment.project_id.in_(project_ids),
                OpportunityAssessment.is_current.is_(True),
            )
        ).all()
    }
    current_results = {
        project_id: QualificationService(session).evaluate(project_id, persist=False)
        for project_id in current_assessments
    }
    quality_counts: dict[UUID, int] = {
        project_id: int(count)
        for project_id, count in session.execute(
            sa.select(QualityFlag.project_id, sa.func.count(QualityFlag.id))
            .where(QualityFlag.project_id.in_(project_ids))
            .group_by(QualityFlag.project_id)
        ).all()
        if project_id is not None
    }
    relationships: dict[UUID, list[dict[str, object]]] = {}
    for relationship, organization in session.execute(
        sa.select(ProjectOrganization, Organization)
        .join(Organization, ProjectOrganization.organization_id == Organization.id)
        .where(ProjectOrganization.project_id.in_(project_ids))
        .order_by(ProjectOrganization.role, Organization.canonical_name)
    ).all():
        relationships.setdefault(relationship.project_id, []).append(
            {
                "organization_id": str(organization.id),
                "organization": organization.canonical_name,
                "role": relationship.role,
                "verification_state": relationship.verification_state.value,
            }
        )
    group_ids = {project.project_group_id for project in projects if project.project_group_id}
    groups = {
        group.id: group
        for group in session.scalars(
            sa.select(ProjectGroup).where(ProjectGroup.id.in_(group_ids))
        ).all()
    }

    items: list[dict[str, object]] = []
    coverage_counts = {state.value: 0 for state in AssessmentCoverage}
    for project in projects:
        project_observations = by_project.get(project.id, [])
        usable_fields = {
            observation.field_name
            for observation in project_observations
            if _observation_has_value(observation)
        }
        assessment = current_assessments.get(project.id)
        coverage_detail = coverage_by_project[project.id]
        coverage = coverage_detail.state.value
        coverage_counts[coverage] += 1
        sections = sorted(
            {
                observation.normalized_text
                for observation in project_observations
                if observation.field_name == "company_report.project.section"
                and observation.normalized_text
            }
        )
        roles = sorted(
            {
                observation.normalized_text
                for observation in project_observations
                if observation.field_name == "company_report.project.role"
                and observation.normalized_text
            }
        )
        source_occurrences = sum(
            observation.field_name == "company_report.project.section"
            for observation in project_observations
        )
        source_dates = [
            value
            for observation in project_observations
            for value in (observation.freshness_at, observation.observed_at)
            if value is not None
        ]
        report_dates = [
            document.report_date
            for observation in project_observations
            if (document := documents_by_id.get(observation.document_id)) is not None
            and document.report_date is not None
        ]
        latest_source_at = max(source_dates or report_dates, default=None)
        if latest_source_at is None:
            freshness_band = "UNKNOWN"
        else:
            aware = latest_source_at.replace(tzinfo=UTC) if latest_source_at.tzinfo is None else latest_source_at.astimezone(UTC)
            age_days = max((datetime.now(UTC) - aware).days, 0)
            freshness_band = "CURRENT" if age_days <= 90 else "RECENT" if age_days <= 365 else "HISTORICAL"
        bid_dates = sorted(
            observation.normalized_date
            for observation in project_observations
            if observation.field_name == "company_report.project.bid_date"
            and observation.normalized_date is not None
        )
        current = current_results.get(project.id)
        group = groups.get(project.project_group_id) if project.project_group_id else None
        warning_count = int(quality_counts.get(project.id, 0))
        items.append(
            {
                **_project_dict(project),
                "featured_case": project.external_id == "1007341663",
                "source_sections": sections,
                "source_occurrence_count": source_occurrences,
                "source_roles": roles,
                "source_bid_date": bid_dates[-1].isoformat() if bid_dates else None,
                "source_contact_available": any(
                    observation.field_name == "company_report.project.contact"
                    and _observation_has_value(observation)
                    for observation in project_observations
                ),
                "source_freshness_at": latest_source_at.isoformat() if latest_source_at else None,
                "source_freshness_band": freshness_band,
                "relationships": relationships.get(project.id, []),
                "assessment_coverage": coverage,
                "coverage_explanation": (
                    "A current full qualification is supported by dedicated project evidence."
                    if coverage == "FULL"
                    else "A project source exists but material evidence is incomplete."
                    if coverage == "PARTIAL"
                    else "This company-history record requires a detailed project report before full qualification."
                    if coverage == "SOURCE_ONLY"
                    else "The persisted source fields do not support a defensible commercial assessment."
                ),
                "source_report_types": list(coverage_detail.report_types),
                "source_document_count": coverage_detail.source_document_count,
                "coverage_reason_codes": list(coverage_detail.reason_codes),
                "commercial_fit_score": str(current.commercial_fit_score) if current else None,
                "commercial_band": current.overall_band if current else None,
                "data_confidence_score": str(current.data_confidence_score) if current else None,
                "data_confidence": assessment.confidence_state.value if assessment else None,
                "operational_action": current.operational_action if current else None,
                "quality_warning_count": warning_count,
                "quality_state": "NEEDS_REVIEW" if warning_count else "NO_OPEN_PROJECT_WARNING",
                "project_group": None
                if group is None
                else {
                    "id": str(group.id),
                    "canonical_name": group.canonical_name,
                    "group_type": group.group_type,
                },
                "available_source_field_count": len(usable_fields),
            }
        )

    return {
        "summary": {
            "source_documents": len(source_documents),
            "detailed_project_documents": sum(
                (document.report_type or "").upper() == "PROJECT"
                for document in source_documents
            ),
            "company_documents": sum(
                (document.report_type or "").upper() == "COMPANY"
                for document in source_documents
            ),
            "detailed_project_records": sum(
                coverage.state is AssessmentCoverage.FULL
                for coverage in coverage_by_project.values()
            ),
            "source_project_rows": sum(
                observation.field_name == "company_report.project.section"
                for observation in observations
            ),
            "canonical_projects": len(projects),
            "projects_assessed": len(current_assessments),
            "projects_partially_assessable": coverage_counts["PARTIAL"],
            "company_history_projects": sum(
                "COMPANY" in coverage.report_types
                for coverage in coverage_by_project.values()
            ),
            "source_only_projects": coverage_counts["SOURCE_ONLY"],
            "projects_with_insufficient_evidence": coverage_counts["INSUFFICIENT"],
            "project_quality_warnings": sum(quality_counts.values()),
            "coverage_counts": coverage_counts,
        },
        "items": items,
        "count": len(items),
        "semantics": {
            "source_rows": "Source rows may repeat a project or represent related phases; they are not independent opportunities.",
            "assessment_coverage": "Unassessed does not mean rejected. Coverage reflects the evidence available in persisted source records.",
            "scores": "Commercial Fit and Data Confidence are returned only for supported current assessments.",
        },
    }


@router.post("/portfolio/triage")
def triage_project_batch(
    payload: BatchTriageRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    """Compute deterministic batch routing without persistence or external writes."""
    return BatchProjectTriageService(session).run(payload.project_ids)


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
    return {
        "items": [_project_dict(row) for row in rows],
        "count": len(rows),
        "limit": limit,
        "offset": offset,
    }


@router.get("/projects/{project_id}")
def get_project(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    return _project_dict(_project_or_404(session, project_id))


@router.get("/projects/{project_id}/organizations")
def get_project_organizations(
    project_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    project = _project_or_404(session, project_id)
    rows = session.execute(
        sa.select(ProjectOrganization, Organization)
        .join(Organization, ProjectOrganization.organization_id == Organization.id)
        .where(ProjectOrganization.project_id == project_id)
        .order_by(ProjectOrganization.role, Organization.canonical_name)
    ).all()
    group = (
        session.get(ProjectGroup, project.project_group_id) if project.project_group_id else None
    )
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
                "reported_value": str(row.reported_value)
                if row.reported_value is not None
                else None,
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
def get_project_signals(
    project_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    _project_or_404(session, project_id)
    rows = session.scalars(
        sa.select(ProjectSignal)
        .where(ProjectSignal.project_id == project_id)
        .order_by(ProjectSignal.signal_key)
    ).all()
    return {
        "project_id": str(project_id),
        "items": [
            {
                "id": str(row.id),
                "key": row.signal_key,
                "value": row.signal_value,
                "classification": row.classification.value,
                "confidence_score": str(row.confidence_score)
                if row.confidence_score is not None
                else None,
                "source_observation_id": str(row.source_observation_id)
                if row.source_observation_id
                else None,
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
        .where(
            SourceObservation.project_id == project_id,
            SourceEvidence.is_permitted_for_decision.is_(True),
        )
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
    return {
        "project_id": str(project_id),
        "items": items,
        "count": len(items),
        "demo_mode": policy.demo_mode,
    }


@router.get("/projects/{project_id}/quality")
def get_project_quality(
    project_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    _project_or_404(session, project_id)
    severity_rank = sa.case(
        (QualityFlag.severity == QualitySeverity.CRITICAL, 5),
        (QualityFlag.severity == QualitySeverity.HIGH, 4),
        (QualityFlag.severity == QualitySeverity.MEDIUM, 3),
        (QualityFlag.severity == QualitySeverity.LOW, 2),
        else_=1,
    )
    rows = session.scalars(
        sa.select(QualityFlag)
        .where(QualityFlag.project_id == project_id)
        .order_by(
            QualityFlag.blocks_progression.desc(), severity_rank.desc(), QualityFlag.created_at
        )
    ).all()
    return {
        "project_id": str(project_id),
        "items": [
            {
                "id": str(row.id),
                "rule_code": row.rule_code,
                "severity": row.severity.value,
                "state": row.state.value,
                "review_status": (
                    "NEEDS_REVIEW"
                    if row.state in {QualityFlagState.OPEN, QualityFlagState.ACKNOWLEDGED}
                    else row.state.value
                ),
                "title": row.title,
                "detail": row.detail,
                "decision_impact": row.decision_impact,
                "blocks_progression": row.blocks_progression,
                "recommended_action": quality_warning_action(row.rule_code),
            }
            for row in rows
        ],
    }


@router.get("/projects/{project_id}/assessment")
def get_project_assessment(
    project_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    _project_or_404(session, project_id)
    assessment = session.scalar(
        sa.select(OpportunityAssessment).where(
            OpportunityAssessment.project_id == project_id,
            OpportunityAssessment.is_current.is_(True),
        )
    )
    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ASSESSMENT_NOT_FOUND", "message": "Run qualification first."},
        )
    factors = session.scalars(
        sa.select(AssessmentFactor)
        .where(AssessmentFactor.assessment_id == assessment.id)
        .order_by(AssessmentFactor.factor_key)
    ).all()
    current = QualificationService(session).evaluate(project_id, persist=False)
    return {
        "project_id": str(project_id),
        "assessment": {
            "id": str(assessment.id),
            "commercial_fit_score": str(current.commercial_fit_score),
            "data_confidence_score": str(current.data_confidence_score),
            "disposition": current.disposition,
            "overall_band": current.overall_band,
            "operational_action": current.operational_action,
            "model_version": current.model_version,
            "score_semantics": "Internal deterministic ordering only; not a probability, forecast, or verified demand.",
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
        "dimensions": jsonable(current.dimensions),
        "product_fits": [
            {
                "product_code": row.product_code,
                "characteristic_relevance_score": str(row.fit_score),
                "fit_band": row.applicability_status,
                "applicability_status": row.applicability_status,
                "classification": row.classification.value,
                "confidence_state": row.confidence_state.value,
                "explanation": row.explanation,
                "supporting_evidence": list(row.supporting_evidence),
                "contradicting_evidence": list(row.contradicting_evidence),
                "missing_evidence": list(row.missing_evidence),
            }
            for row in current.product_fits
        ],
        "comparison_cohorts": jsonable(current.comparison_cohorts),
        "highest_value_next_verification": (
            jsonable(current.decision_changing_unknowns[0])
            if current.decision_changing_unknowns
            else None
        ),
        "notes": list(current.notes),
    }


@router.post("/projects/{project_id}/sensitivity")
def run_project_sensitivity(
    project_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    _project_or_404(session, project_id)
    result = QualificationService(session).evaluate(project_id, persist=False)
    return {
        "project_id": str(project_id),
        "baseline": {
            "commercial_fit_score": str(result.commercial_fit_score),
            "disposition": result.disposition,
            "overall_band": result.overall_band,
            "operational_action": result.operational_action,
        },
        "counterfactuals": jsonable(result.counterfactuals),
        "what_would_change_my_mind": jsonable(result.what_would_change_my_mind),
        "decision_changing_unknowns": jsonable(result.decision_changing_unknowns),
        "persisted": False,
    }
