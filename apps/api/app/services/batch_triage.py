from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import OpportunityAssessment, Project, QualityFlag, SourceDocument, SourceObservation
from app.scoring.qualification import QualificationService


class AssessmentCoverage(StrEnum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    SOURCE_ONLY = "SOURCE_ONLY"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class ProjectCoverage:
    project_id: UUID
    state: AssessmentCoverage
    report_types: tuple[str, ...]
    source_document_count: int
    reason_codes: tuple[str, ...]


def derive_project_coverage(session: Session, project_ids: list[UUID]) -> dict[UUID, ProjectCoverage]:
    """Derive evidence depth from source provenance, never from a populated-field score."""
    report_types: dict[UUID, set[str]] = {project_id: set() for project_id in project_ids}
    document_ids: dict[UUID, set[UUID]] = {project_id: set() for project_id in project_ids}
    if project_ids:
        for project_id, document_id, report_type in session.execute(
            sa.select(
                SourceObservation.project_id,
                SourceObservation.document_id,
                SourceDocument.report_type,
            )
            .join(SourceDocument, SourceDocument.id == SourceObservation.document_id)
            .where(SourceObservation.project_id.in_(project_ids))
            .distinct()
        ).all():
            if project_id is None:
                continue
            document_ids[project_id].add(document_id)
            if report_type:
                report_types[project_id].add(report_type.upper())

    result: dict[UUID, ProjectCoverage] = {}
    for project_id in project_ids:
        types = report_types[project_id]
        reasons: tuple[str, ...]
        if "PROJECT" in types:
            state = AssessmentCoverage.FULL
            reasons = ("DETAILED_PROJECT_REPORT_AVAILABLE",)
        elif "COMPANY" in types:
            state = AssessmentCoverage.SOURCE_ONLY
            reasons = ("COMPANY_HISTORY_SOURCE_ONLY", "DETAILED_PROJECT_REPORT_REQUIRED")
        elif types:
            state = AssessmentCoverage.PARTIAL
            reasons = ("PROJECT_SOURCE_PROVENANCE_INCOMPLETE",)
        else:
            state = AssessmentCoverage.INSUFFICIENT
            reasons = ("NO_PROJECT_SOURCE_DOCUMENT",)
        result[project_id] = ProjectCoverage(
            project_id=project_id,
            state=state,
            report_types=tuple(sorted(types)),
            source_document_count=len(document_ids[project_id]),
            reason_codes=reasons,
        )
    return result


class BatchProjectTriageService:
    """Unattended, deterministic orchestration for candidate project batches.

    The service performs no commits and invokes qualification with ``persist=False``.
    Repeating the same batch against unchanged source state returns the same result.
    """

    def __init__(self, session: Session):
        self.session = session

    def run(self, project_ids: list[UUID]) -> dict[str, object]:
        unique_ids = list(dict.fromkeys(project_ids))
        projects = {
            project.id: project
            for project in self.session.scalars(
                sa.select(Project).where(
                    Project.id.in_(unique_ids),
                    Project.is_synthetic.is_(False),
                )
            ).all()
        }
        ordered_ids = [project_id for project_id in unique_ids if project_id in projects]
        coverage = derive_project_coverage(self.session, ordered_ids)
        current_assessments = {
            row.project_id: row
            for row in self.session.scalars(
                sa.select(OpportunityAssessment).where(
                    OpportunityAssessment.project_id.in_(ordered_ids),
                    OpportunityAssessment.is_current.is_(True),
                )
            ).all()
        }
        quality_counts = {
            project_id: int(count)
            for project_id, count in self.session.execute(
                sa.select(QualityFlag.project_id, sa.func.count(QualityFlag.id))
                .where(QualityFlag.project_id.in_(ordered_ids))
                .group_by(QualityFlag.project_id)
            ).all()
            if project_id is not None
        }

        items: list[dict[str, object]] = []
        ranked: list[dict[str, object]] = []
        for project_id in ordered_ids:
            project = projects[project_id]
            state = coverage[project_id]
            assessment = None
            if state.state is AssessmentCoverage.FULL:
                assessment = QualificationService(self.session).evaluate(project_id, persist=False)
            item: dict[str, object] = {
                "project_id": str(project_id),
                "external_id": project.external_id,
                "project": project.canonical_name,
                "assessment_coverage": state.state.value,
                "report_types": list(state.report_types),
                "source_document_count": state.source_document_count,
                "reason_codes": list(state.reason_codes),
                "assessed": assessment is not None,
                "quality_warning_count": quality_counts.get(project_id, 0),
                "review_required": bool(quality_counts.get(project_id, 0)),
                "commercial_fit_score": str(assessment.commercial_fit_score) if assessment else None,
                "commercial_band": assessment.overall_band if assessment else None,
                "operational_action": assessment.operational_action if assessment else None,
                "data_confidence": (
                    current_assessments[project_id].confidence_state.value
                    if assessment and project_id in current_assessments
                    else None
                ),
            }
            items.append(item)
            if assessment is not None:
                ranked.append(item)

        ranked.sort(
            key=lambda item: (
                -float(str(item["commercial_fit_score"])),
                str(item["external_id"] or ""),
            )
        )
        counts = {state.value: 0 for state in AssessmentCoverage}
        for row in items:
            counts[str(row["assessment_coverage"])] += 1
        return {
            "total_records": len(items),
            "full_eligible": counts[AssessmentCoverage.FULL.value],
            "partial": counts[AssessmentCoverage.PARTIAL.value],
            "source_only": counts[AssessmentCoverage.SOURCE_ONLY.value],
            "insufficient": counts[AssessmentCoverage.INSUFFICIENT.value],
            "assessed": len(ranked),
            "review_required": sum(bool(item["review_required"]) for item in items),
            "ranked_assessments": ranked,
            "items": items,
            "external_writes_executed": 0,
            "semantics": "Only FULL detailed-project records are qualified and ordered. Company-history records remain unscored.",
        }
