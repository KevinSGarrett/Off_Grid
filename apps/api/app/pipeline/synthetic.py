from __future__ import annotations

import hashlib
import random
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import (
    ConfidenceState,
    EvidenceClassification,
    ProjectState,
    ScoringTreatment,
    ValidationState,
    ValueType,
    VerificationState,
)
from app.models import Organization, Project, ProjectOrganization, SourceDocument, SourceObservation
from app.scoring.qualification import QualificationService

SYNTHETIC_DATASET_VERSION = "synthetic-scale-1.0"


@dataclass(frozen=True, slots=True)
class SyntheticProjectSpec:
    external_id: str
    name: str
    sector: str
    city: str
    region: str
    estimated_value: int
    data_center: bool
    new_construction: bool
    site_work: bool
    paving: bool
    multi_phase: bool
    gc_awarded: bool
    named_gc_contact: bool
    label: str = "SYNTHETIC"
    is_synthetic: bool = True


@dataclass(frozen=True, slots=True)
class SyntheticSeedResult:
    requested: int
    created: int
    duplicates_prevented: int
    project_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticLoadResult:
    dataset_version: str
    requested: int
    created: int
    duplicates_prevented: int
    evaluated: int
    pursue: int
    review: int
    passed: int
    seed_seconds: float
    scoring_seconds: float
    total_seconds: float
    projects_per_second: float
    external_writes_executed: int
    all_records_synthetic: bool


def generate_synthetic_projects(*, count: int = 300, seed: int = 1401) -> tuple[SyntheticProjectSpec, ...]:
    """Generate deterministic, unmistakably synthetic normalized project fixtures.

    This dataset exists only to exercise scale, prioritization and idempotency. It must never be
    used as evidence for Stafford/EE Reed or any employer-facing factual claim.
    """

    if count < 1:
        raise ValueError("count must be >= 1")
    rng = random.Random(seed)
    sectors = ("data_center", "warehouse", "medical", "office", "industrial")
    cities = (("Houston", "TX"), ("Fredericksburg", "VA"), ("Austin", "TX"), ("Savannah", "GA"))
    values = (500_000, 4_000_000, 18_000_000, 75_000_000, 250_000_000, 1_000_000_000)
    rows: list[SyntheticProjectSpec] = []
    for index in range(1, count + 1):
        sector = rng.choice(sectors)
        city, region = rng.choice(cities)
        data_center = sector == "data_center"
        new_construction = rng.random() < 0.76
        site_work = rng.random() < (0.82 if data_center else 0.52)
        paving = rng.random() < (0.70 if site_work else 0.18)
        multi_phase = rng.random() < (0.58 if data_center else 0.25)
        gc_awarded = rng.random() < 0.67
        named_gc_contact = rng.random() < 0.45
        rows.append(
            SyntheticProjectSpec(
                external_id=f"SYNTHETIC-{seed}-{index:05d}",
                name=f"SYNTHETIC Project {index:05d} - {sector.replace('_', ' ').title()}",
                sector=sector,
                city=city,
                region=region,
                estimated_value=rng.choice(values),
                data_center=data_center,
                new_construction=new_construction,
                site_work=site_work,
                paving=paving,
                multi_phase=multi_phase,
                gc_awarded=gc_awarded,
                named_gc_contact=named_gc_contact,
            )
        )
    return tuple(rows)


def specs_as_jsonable(specs: Iterable[SyntheticProjectSpec]) -> list[dict[str, object]]:
    return [asdict(spec) for spec in specs]


def _hash(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _add_observation(
    session: Session,
    *,
    doc: SourceDocument,
    project: Project,
    field: str,
    raw: str,
    value_type: ValueType = ValueType.TEXT,
    normalized_text: str | None = None,
    normalized_decimal: Decimal | None = None,
    normalized_date: date | None = None,
    confidence: Decimal = Decimal("0.95"),
) -> SourceObservation:
    obs = SourceObservation(
        document_id=doc.id,
        project_id=project.id,
        field_name=field,
        value_type=value_type,
        raw_value=raw,
        normalized_text=normalized_text,
        normalized_decimal=normalized_decimal,
        normalized_date=normalized_date,
        observation_fingerprint=_hash(doc.content_sha256, project.external_id, field, raw),
        evidence_classification=EvidenceClassification.EXPLICIT,
        confidence_state=ConfidenceState.HIGH,
        confidence_score=confidence,
        validation_state=ValidationState.VALID,
        scoring_treatment=ScoringTreatment.FULL,
        decision_eligible=True,
        decision_eligibility_reason="Synthetic scale fixture: deterministic normalized evidence.",
        observed_at=doc.report_date,
        freshness_at=doc.report_date,
        is_synthetic=True,
    )
    session.add(obs)
    session.flush()
    return obs


def seed_synthetic_portfolio(session: Session, specs: Iterable[SyntheticProjectSpec]) -> SyntheticSeedResult:
    rows = tuple(specs)
    created = 0
    duplicates = 0
    ids: list[str] = []
    now = datetime.now(timezone.utc)
    for spec in rows:
        key = f"synthetic:{spec.external_id}"
        existing = session.scalar(sa.select(Project).where(Project.canonical_key == key))
        if existing is not None:
            duplicates += 1
            ids.append(str(existing.id))
            continue

        project = Project(
            canonical_name=spec.name,
            normalized_name=spec.name.lower(),
            canonical_key=key,
            source_system="synthetic_scale_fixture",
            external_id=spec.external_id,
            state=ProjectState.PARSED,
            stage="POST BID - General Contractor Award" if spec.gc_awarded else "Planning",
            category=spec.sector,
            city=spec.city,
            region=spec.region,
            country_code="US",
            reported_value=Decimal(spec.estimated_value),
            currency_code="USD",
            start_date=date(2027, 1, 15),
            phase_label="Phases 1 & 2" if spec.multi_phase else None,
            is_synthetic=True,
        )
        session.add(project)
        session.flush()
        doc = SourceDocument(
            source_type="synthetic_scale_fixture",
            source_system="synthetic_scale_fixture",
            external_id=spec.external_id,
            report_type="SYNTHETIC_PROJECT",
            original_filename=f"{spec.external_id}.json",
            content_sha256=_hash(SYNTHETIC_DATASET_VERSION, spec.external_id),
            blob_ref=f"synthetic://{spec.external_id}",
            mime_type="application/json",
            byte_size=0,
            report_date=now,
            imported_at=now,
            parser_version=SYNTHETIC_DATASET_VERSION,
            is_synthetic=True,
            is_private=False,
        )
        session.add(doc)
        session.flush()

        scope_parts = ["construction"]
        if spec.data_center:
            scope_parts.append("data center")
        if spec.new_construction:
            scope_parts.append("new construction")
        if spec.site_work:
            scope_parts.append("site work")
        if spec.paving:
            scope_parts.append("paving")
        scope = ", ".join(scope_parts)
        description = (
            f"SYNTHETIC scale fixture for {spec.sector}. "
            + ("A synthetic multi-phased development with phases 1 & 2 are underway." if spec.multi_phase else "Single-phase synthetic project.")
            + (" Synthetic broader campus includes 20 data center buildings and $10 billion projection." if spec.data_center and spec.multi_phase else "")
        )
        notes = "New Construction, Paving, Site Work" if spec.new_construction and spec.site_work and spec.paving else scope
        _add_observation(session, doc=doc, project=project, field="project.external_id", raw=spec.external_id, normalized_text=spec.external_id)
        scope_obs = _add_observation(session, doc=doc, project=project, field="project.scope", raw=scope, normalized_text=scope)
        _add_observation(session, doc=doc, project=project, field="project.description", raw=description, normalized_text=description)
        _add_observation(session, doc=doc, project=project, field="project.notes", raw=notes, normalized_text=notes)
        stage_text = "POST BID - General Contractor Award" if spec.gc_awarded else "Planning"
        stage_obs = _add_observation(session, doc=doc, project=project, field="project.stage", raw=stage_text, normalized_text=stage_text)
        _add_observation(
            session,
            doc=doc,
            project=project,
            field="project.reported_value",
            raw=str(spec.estimated_value),
            value_type=ValueType.MONEY,
            normalized_decimal=Decimal(spec.estimated_value),
        )
        _add_observation(
            session,
            doc=doc,
            project=project,
            field="project.start_date",
            raw="2027-01-15",
            value_type=ValueType.DATE,
            normalized_date=date(2027, 1, 15),
        )
        org = Organization(
            canonical_name=f"SYNTHETIC GC {spec.external_id}",
            normalized_name=f"synthetic gc {spec.external_id}".lower(),
            canonical_key=f"synthetic:org:{spec.external_id}",
            organization_type="CONTRACTOR",
            notes="SYNTHETIC scale fixture only.",
        )
        session.add(org)
        session.flush()
        gc_obs = _add_observation(
            session,
            doc=doc,
            project=project,
            field="project.general_contractor",
            raw=org.canonical_name,
            normalized_text=org.canonical_name,
        )
        session.add(
            ProjectOrganization(
                project_id=project.id,
                organization_id=org.id,
                role="General Contractor",
                verification_state=VerificationState.SUPPORTED,
                source_observation_id=gc_obs.id,
            )
        )
        if not spec.named_gc_contact:
            from app.models import QualityFlag
            from app.domain.states import QualitySeverity

            session.add(
                QualityFlag(
                    rule_code="MISSING_PROJECT_GC_CONTACT",
                    severity=QualitySeverity.MEDIUM,
                    project_id=project.id,
                    observation_id=scope_obs.id,
                    title="SYNTHETIC missing named project-level GC contact",
                    detail="SYNTHETIC scale fixture intentionally omits a named project-level GC contact.",
                    decision_impact="VERY_HIGH",
                    blocks_progression=False,
                    first_detected_at=now,
                )
            )
        # Keep stage observation reachable for future load diagnostics and prevent unused fixture drift.
        assert stage_obs.id is not None
        created += 1
        ids.append(str(project.id))
    session.commit()
    return SyntheticSeedResult(
        requested=len(rows),
        created=created,
        duplicates_prevented=duplicates,
        project_ids=tuple(ids),
    )


def run_synthetic_load(
    session: Session,
    *,
    count: int = 300,
    seed: int = 1401,
) -> SyntheticLoadResult:
    total_started = time.perf_counter()
    specs = generate_synthetic_projects(count=count, seed=seed)
    seed_started = time.perf_counter()
    seed_result = seed_synthetic_portfolio(session, specs)
    seed_seconds = max(time.perf_counter() - seed_started, 0.000001)
    projects = session.scalars(
        sa.select(Project)
        .where(Project.source_system == "synthetic_scale_fixture")
        .order_by(Project.external_id)
    ).all()
    started = time.perf_counter()
    dispositions = {"PURSUE": 0, "REVIEW": 0, "PASS": 0}
    service = QualificationService(session)
    evaluated = 0
    for project in projects:
        result = service.evaluate(project.id, persist=False)
        dispositions[result.disposition] += 1
        evaluated += 1
    scoring_seconds = max(time.perf_counter() - started, 0.000001)
    total_seconds = max(time.perf_counter() - total_started, 0.000001)
    all_synthetic = all(project.is_synthetic for project in projects)
    return SyntheticLoadResult(
        dataset_version=SYNTHETIC_DATASET_VERSION,
        requested=count,
        created=seed_result.created,
        duplicates_prevented=seed_result.duplicates_prevented,
        evaluated=evaluated,
        pursue=dispositions["PURSUE"],
        review=dispositions["REVIEW"],
        passed=dispositions["PASS"],
        seed_seconds=round(seed_seconds, 6),
        scoring_seconds=round(scoring_seconds, 6),
        total_seconds=round(total_seconds, 6),
        projects_per_second=round(evaluated / total_seconds, 3),
        external_writes_executed=0,
        all_records_synthetic=all_synthetic,
    )
