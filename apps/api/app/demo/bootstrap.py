from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa

from app.commercial_workflow.service import CommercialWorkflowService
from app.contact_resolution.service import ContactResolutionService
from app.crm.service import CommercialIntegrationResult, CommercialIntegrationService
from app.ingestion.service import ConstructConnectIngestionService
from app.models import Base, Organization, Project
from app.persistence.database import build_engine, build_session_factory
from app.resolution.service import ProjectAccountResolutionService
from app.scoring.qualification import QualificationService
from app.scoring.types import QualificationResult


@dataclass(frozen=True, slots=True)
class DemoBootstrapResult:
    database_path: Path
    project_id: UUID
    organization_id: UUID
    project_external_id: str
    organization_canonical_key: str
    assessment: QualificationResult
    integrations: CommercialIntegrationResult


def build_real_demo_database(
    *,
    database_path: str | Path,
    stafford_pdf: str | Path,
    ee_reed_pdf: str | Path,
    reset: bool = True,
) -> DemoBootstrapResult:
    """Build the canonical Stafford/EE Reed demo state from the supplied real PDFs.

    This is intentionally a local/private bootstrap path. It runs the same domain services used
    by the application instead of inserting precomputed scores or hard-coded API answers. A
    deployment-safe derivative snapshot can be created from this database by the public seed
    builder after contact details are masked.
    """

    db = Path(database_path).resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    if reset and db.exists():
        db.unlink()

    engine = build_engine(f"sqlite+pysqlite:///{db}")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)

    with factory() as session:
        ingest = ConstructConnectIngestionService(session)
        ingest.ingest(Path(stafford_pdf))
        ingest.ingest(Path(ee_reed_pdf))

        project = session.scalar(
            sa.select(Project).where(
                Project.source_system == "constructconnect",
                Project.external_id == "1007341663",
            )
        )
        organization = session.scalar(
            sa.select(Organization).where(
                Organization.canonical_key == "constructconnect:company:1000647848"
            )
        )
        if project is None or organization is None:
            raise RuntimeError("Real golden bootstrap did not produce Stafford and EE Reed")

        assessment = QualificationService(session).evaluate(project.id, persist=True)
        ProjectAccountResolutionService(session).run()
        ContactResolutionService(session).run(project_external_id="1007341663")
        CommercialWorkflowService(session).run(project_external_id="1007341663")
        integrations = CommercialIntegrationService(session, demo_mode=True).run("1007341663")

        result = DemoBootstrapResult(
            database_path=db,
            project_id=project.id,
            organization_id=organization.id,
            project_external_id=project.external_id or "",
            organization_canonical_key=organization.canonical_key,
            assessment=assessment,
            integrations=integrations,
        )
    engine.dispose()
    return result
