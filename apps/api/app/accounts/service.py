from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import (
    Organization,
    OrganizationAlias,
    OrganizationDomain,
    Project,
    ProjectOrganization,
    QualityFlag,
    SourceDocument,
    SourceObservation,
)
from app.resolution.people import PersonResolutionService
from app.resolution.types import AccountActivityBand, AccountIntelligenceResult
from app.scoring.config import load_yaml_config


def _project_type(name: str) -> str:
    n = name.lower()
    groups = [
        ("DATA_CENTER_TECH", ("technology campus", "data center", "data centre")),
        ("WAREHOUSE_LOGISTICS", ("warehouse", "distribution", "logistics", "freight", "industrial park")),
        ("MEDICAL_HEALTH", ("medical", "hospital", "surgery", "clinic", "health")),
        ("OFFICE", ("office", "headquarters")),
        ("HOSPITALITY", ("hotel", "hilton", "hyatt", "westin")),
        ("EDUCATION", ("college", "school", "university", "instructional", "academic")),
        ("CIVIC_INFRASTRUCTURE", ("county", "city hall", "fire station", "utilities", "water", "sewer", "pavement")),
    ]
    for label, tokens in groups:
        if any(token in n for token in tokens):
            return label
    return "OTHER_UNKNOWN"


class AccountIntelligenceService:
    def __init__(self, session: Session):
        self.session = session
        cfg = load_yaml_config("config/entity_resolution.yaml").data["entity_resolution"]
        self.config = cfg["account_intelligence"]

    def analyze(self, organization_id: UUID) -> AccountIntelligenceResult:
        org = self.session.get(Organization, organization_id)
        if org is None:
            raise ValueError(f"Organization not found: {organization_id}")

        aliases = tuple(sorted({x.alias for x in self.session.scalars(sa.select(OrganizationAlias).where(OrganizationAlias.organization_id == org.id)).all()}))
        domains = self.session.scalars(sa.select(OrganizationDomain).where(OrganizationDomain.organization_id == org.id)).all()
        domain_states = {d.normalized_domain: d.relationship_state.value for d in sorted(domains, key=lambda x: x.normalized_domain)}

        section_obs = list(self.session.scalars(sa.select(SourceObservation).where(SourceObservation.organization_id == org.id, SourceObservation.field_name == "company_report.project.section")).all())
        section_counts = Counter((o.normalized_text or "UNKNOWN") for o in section_obs)
        source_project_rows = len(section_obs)

        project_ids = {o.project_id for o in section_obs if o.project_id is not None}
        projects = list(self.session.scalars(sa.select(Project).where(Project.id.in_(project_ids))).all()) if project_ids else []
        project_map = {p.id: p for p in projects}
        geography_counts = Counter(f"{p.city or 'UNKNOWN'}, {p.region or 'UNKNOWN'}" for p in projects)
        type_counts = Counter(_project_type(p.canonical_name) for p in projects)

        external_id = org.canonical_key.rsplit(":", 1)[-1] if org.canonical_key.startswith("constructconnect:company:") else None
        company_doc_stmt = sa.select(SourceDocument).where(SourceDocument.report_type == "COMPANY")
        if external_id:
            company_doc_stmt = company_doc_stmt.where(SourceDocument.external_id == external_id)
        company_doc = self.session.scalar(company_doc_stmt.order_by(SourceDocument.report_date.desc()))
        as_of = company_doc.report_date.date() if company_doc and company_doc.report_date else None
        recent_cutoff = as_of - timedelta(days=int(self.config["recent_activity_days"])) if as_of else None

        bid_obs = list(self.session.scalars(sa.select(SourceObservation).where(SourceObservation.organization_id == org.id, SourceObservation.field_name == "company_report.project.bid_date")).all())
        bid_by_project: dict[UUID, list] = defaultdict(list)
        for obs in bid_obs:
            if obs.project_id and obs.normalized_date:
                bid_by_project[obs.project_id].append(obs.normalized_date)
        sections_by_project: dict[UUID, set[str]] = defaultdict(set)
        for obs in section_obs:
            if obs.project_id:
                sections_by_project[obs.project_id].add(obs.normalized_text or "UNKNOWN")

        row_bands = Counter()
        band_projects: dict[str, set[UUID]] = defaultdict(set)
        for obs in section_obs:
            pid = obs.project_id
            section = obs.normalized_text or "UNKNOWN"
            dates = bid_by_project.get(pid, []) if pid else []
            if section in set(self.config["current_source_sections"]):
                band = "CURRENT_SOURCE_SECTION"
            elif dates and recent_cutoff and max(dates) >= recent_cutoff:
                band = "RECENT_DATED"
            elif dates and recent_cutoff and max(dates) < recent_cutoff:
                band = "HISTORICAL_DATED"
            else:
                band = "UNDATED_UNKNOWN_FRESHNESS"
            row_bands[band] += 1
            if pid:
                band_projects[band].add(pid)
        activity = tuple(AccountActivityBand(band=b, source_row_count=row_bands[b], unique_project_count=len(band_projects[b])) for b in sorted(row_bands))

        recurrence = PersonResolutionService(self.session).recurrence_signals(org.id)
        qflags = self.session.scalars(sa.select(QualityFlag).where(QualityFlag.organization_id == org.id)).all()
        quality_counts = Counter(flag.rule_code for flag in qflags)

        recent_unique = len(band_projects.get("CURRENT_SOURCE_SECTION", set()) | band_projects.get("RECENT_DATED", set()))
        if len(projects) >= int(self.config["strong_repeat_unique_projects_min"]) and recent_unique >= int(self.config["strong_recent_unique_projects_min"]):
            strategic_band = "STRONG_REPEAT_ACTIVITY"
        elif len(projects) >= 20:
            strategic_band = "MEANINGFUL_REPEAT_ACTIVITY"
        else:
            strategic_band = "LIMITED_REPEAT_ACTIVITY"

        entity_state = "REVIEW_DIVISION_RELATIONSHIP" if any(v == "UNKNOWN" for v in domain_states.values()) else "RESOLVED_SOURCE_ACCOUNT"
        recommendation = "INVESTIGATE_AS_STRATEGIC_ACCOUNT" if strategic_band in {"STRONG_REPEAT_ACTIVITY", "MEANINGFUL_REPEAT_ACTIVITY"} else "MONITOR"
        caveats = (
            "Source project rows are not equivalent to independent opportunities; repeated project rows and Stafford phases must not be blindly summed.",
            "Historical/undated source rows are separated from recent/current evidence instead of being treated as current pipeline.",
            "Contact recurrence indicates repeated source association only and never verifies rental authority.",
        )
        return AccountIntelligenceResult(
            organization_id=org.id,
            canonical_name=org.canonical_name,
            source_aliases=aliases,
            source_project_rows=source_project_rows,
            source_section_counts=dict(sorted(section_counts.items())),
            unique_projects=len(projects),
            unique_project_geographies=len(geography_counts),
            geography_counts=dict(geography_counts.most_common()),
            project_type_counts=dict(type_counts.most_common()),
            activity_bands=activity,
            recurring_contacts=recurrence,
            quality_flag_counts=dict(sorted(quality_counts.items())),
            domain_states=domain_states,
            strategic_signal_band=strategic_band,
            entity_resolution_state=entity_state,
            account_recommendation=recommendation,
            caveats=caveats,
        )
