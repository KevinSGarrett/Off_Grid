from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.commercial_workflow.service import Wave09CommercialWorkflowService
from app.contact_resolution.service import Wave08ContactResolutionService
from app.crm.service import Wave10IntegrationService
from app.ingestion.service import ConstructConnectIngestionService
from app.main import create_app
from app.models import Base, Organization, Project
from app.persistence.database import build_engine, build_session_factory
from app.resolution.service import Wave07ResolutionService
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[1]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


@pytest.fixture(scope="session")
def wave14_full_state(tmp_path_factory):
    root = tmp_path_factory.mktemp("wave14-full")
    engine = build_engine(f"sqlite+pysqlite:///{root / 'wave14.db'}")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    with factory() as session:
        ingest = ConstructConnectIngestionService(session)
        stafford_ingest = ingest.ingest(STAFFORD)
        ee_reed_ingest = ingest.ingest(EE_REED)
        project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
        organization = session.scalar(
            sa.select(Organization).where(Organization.canonical_key == "constructconnect:company:1000647848")
        )
        assert project is not None and organization is not None
        assessment = QualificationService(session).evaluate(project.id, persist=True)
        Wave07ResolutionService(session).run()
        Wave08ContactResolutionService(session).run()
        Wave09CommercialWorkflowService(session).run()
        crm = Wave10IntegrationService(session).run()
        ids = {
            "project": project.id,
            "organization": organization.id,
            "stafford_run": stafford_ingest.pipeline_run_id,
            "ee_reed_run": ee_reed_ingest.pipeline_run_id,
        }
    return {
        "root": root,
        "factory": factory,
        "client": TestClient(create_app(session_factory=factory, demo_mode=True, upload_dir=root / "demo_uploads")),
        "internal_client": TestClient(create_app(session_factory=factory, demo_mode=False, upload_dir=root / "internal_uploads")),
        "ids": ids,
        "assessment": assessment,
        "crm": crm,
    }
