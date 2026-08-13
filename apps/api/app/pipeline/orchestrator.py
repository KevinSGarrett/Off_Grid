from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.crm.service import CommercialIntegrationService
from app.ingestion.service import ConstructConnectIngestionService
from app.models import Project
from app.scoring.qualification import QualificationService


@dataclass(frozen=True, slots=True)
class StageResult:
    stage: str
    status: str
    detail: str
    payload: object | None = None


@dataclass(frozen=True, slots=True)
class PipelineOrchestrationResult:
    report_type: str
    pipeline_run_id: UUID
    canonical_entity_id: UUID | None
    stages: tuple[StageResult, ...]


class CommercialPipelineOrchestrator:
    """Thin orchestration over domain-owned services.

    The API orchestrator deliberately does not reimplement domain rules in HTTP handlers. Ingestion and
    qualification are generic. Later Stafford-specific research/commercial snapshots remain owned
    by their prior services and are exposed via query/refresh endpoints rather than silently run for
    unrelated projects.
    """

    def __init__(self, session: Session):
        self.session = session

    def ingest(self, path: str | Path) -> PipelineOrchestrationResult:
        result = ConstructConnectIngestionService(self.session).ingest(Path(path))
        stages: list[StageResult] = [
            StageResult("ingest", "SUCCEEDED", f"Detected {result.report_type}", result),
        ]
        if result.report_type == "PROJECT" and result.canonical_entity_id:
            try:
                qualification = QualificationService(self.session).evaluate(result.canonical_entity_id, persist=True)
                stages.append(StageResult("qualification", "SUCCEEDED", "Project qualified", qualification))
            except Exception as exc:  # fail visibly; owner service persists source/pipeline state
                stages.append(StageResult("qualification", "FAILED", str(exc)))
        else:
            stages.append(StageResult("qualification", "SKIPPED", "Qualification applies to project reports."))
        return PipelineOrchestrationResult(
            report_type=result.report_type,
            pipeline_run_id=result.pipeline_run_id,
            canonical_entity_id=result.canonical_entity_id,
            stages=tuple(stages),
        )

    def refresh_project(self, project_id: UUID) -> tuple[StageResult, ...]:
        project = self.session.get(Project, project_id)
        if project is None:
            raise LookupError(f"Project not found: {project_id}")
        stages: list[StageResult] = []
        qualification = QualificationService(self.session).evaluate(project.id, persist=True)
        stages.append(StageResult("qualification", "SUCCEEDED", "Assessment refreshed", qualification))

        # CRM preview depends on contact and commercial-motion state. It is safe to refresh
        # only when that state already exists; it never performs an external write.
        try:
            crm = CommercialIntegrationService(self.session).run(project.external_id or "")
        except Exception as exc:
            stages.append(StageResult("crm_preview", "SKIPPED", f"Prerequisites not ready: {exc}"))
        else:
            stages.append(StageResult("crm_preview", "SUCCEEDED", "CRM/reporting previews refreshed", crm))
        return tuple(stages)
