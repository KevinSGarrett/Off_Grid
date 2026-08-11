from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.service import AccountIntelligenceService
from app.models import ConfigVersion, Organization, Project
from app.resolution.organizations import OrganizationResolutionService
from app.resolution.people import PersonResolutionService
from app.resolution.projects import ProjectClusteringService, extract_phase_descriptor
from app.resolution.types import Wave07ResolutionResult
from app.scoring.config import load_yaml_config


class Wave07ResolutionService:
    """Orchestrates Wave 7 project clustering, account intelligence and source entity resolution."""

    def __init__(self, session: Session):
        self.session = session
        self.loaded_config = load_yaml_config("config/entity_resolution.yaml")
        self.config = self.loaded_config.data["entity_resolution"]

    @property
    def version(self) -> str:
        return str(self.config["version"])

    def run(self, *, company_external_id: str = "1000647848") -> Wave07ResolutionResult:
        self._persist_config_version()
        org = self.session.scalar(
            sa.select(Organization).where(
                Organization.canonical_key == f"constructconnect:company:{company_external_id}"
            )
        )
        if org is None:
            raise ValueError(f"ConstructConnect source organization not found: {company_external_id}")

        organization_service = OrganizationResolutionService(self.session)
        org_match = organization_service.canonicalize_source_account(org.id)

        stafford = list(
            self.session.scalars(
                sa.select(Project).where(Project.normalized_name.like("stafford technology campus%"))
            ).all()
        )
        phase_projects = [p for p in stafford if extract_phase_descriptor(p.canonical_name).is_phase]
        if len(phase_projects) < 2:
            raise ValueError("Expected at least two Stafford Technology Campus phase records")
        cluster = ProjectClusteringService(self.session).cluster_related_phases([p.id for p in phase_projects])

        person_service = PersonResolutionService(self.session)
        duplicates = person_service.duplicate_candidates(org.id)
        canonical_map = person_service.apply_source_canonicalization(org.id, duplicates)
        links_created = person_service.link_project_contacts(org.id, canonical_map=canonical_map)

        account = AccountIntelligenceService(self.session).analyze(org.id)
        self.session.commit()
        return Wave07ResolutionResult(
            resolution_version=self.version,
            ee_reed_organization_id=org.id,
            organization_match=org_match,
            stafford_cluster=cluster,
            duplicate_people=duplicates,
            account_intelligence=account,
            project_person_links_created=links_created,
        )

    def _persist_config_version(self) -> ConfigVersion:
        existing = self.session.scalar(
            sa.select(ConfigVersion).where(
                ConfigVersion.config_kind == "entity_resolution",
                ConfigVersion.version == self.version,
            )
        )
        if existing is not None:
            return existing
        for active in self.session.scalars(
            sa.select(ConfigVersion).where(ConfigVersion.config_kind == "entity_resolution", ConfigVersion.is_active.is_(True))
        ).all():
            active.is_active = False
        row = ConfigVersion(
            config_kind="entity_resolution",
            version=self.version,
            content_sha256=self.loaded_config.sha256,
            source_path=str(self.loaded_config.path),
            content_text=self.loaded_config.text,
            activated_at=datetime.now(timezone.utc),
            is_active=True,
        )
        self.session.add(row)
        self.session.flush()
        return row
