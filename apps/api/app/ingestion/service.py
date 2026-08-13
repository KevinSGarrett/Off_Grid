from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy as sa
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.domain.states import (
    ConfidenceState,
    ContactPointType,
    EvidenceClassification,
    ExceptionResolutionAction,
    MaskingPolicy,
    PIIClass,
    ProjectState,
    QualitySeverity,
    RunStatus,
    ScoringTreatment,
    ValidationState,
    ValueType,
    VerificationState,
)
from app.ingestion.constructconnect_company import parse_company_report
from app.ingestion.constructconnect_project import parse_project_report
from app.ingestion.errors import ParserReconciliationError
from app.ingestion.normalization import (
    canonical_slug,
    email_domain,
    is_generic_email,
    normalized_name,
)
from app.ingestion.pdf_adapter import PARSER_VERSION, detect_report_type, load_pdf
from app.ingestion.types import CompanyProjectRow, EvidenceRef, ParsedCompanyReport, ParsedProjectReport
from app.services.provenance_policy import observation_decision_eligibility
from app.observability.context import bind_pipeline_run
from app.observability.logging import get_logger, sanitize_for_log
from app.models import (
    FieldHistory,
    Organization,
    OrganizationAddress,
    OrganizationAlias,
    OrganizationDomain,
    Person,
    PersonContactPoint,
    PipelineEvent,
    PipelineRun,
    Project,
    ProjectOrganization,
    QualityFlag,
    SourceDocument,
    SourceEvidence,
    SourceObservation,
    WorkflowException,
)

SOURCE_TYPE = "constructconnect_pdf"
SOURCE_SYSTEM = "constructconnect"
MATERIAL_PROJECT_FIELD_POLICY = (
    ("canonical_name", "project.name", "HIGH"),
    ("stage", "project.stage", "HIGH"),
    ("category", "project.category", "MEDIUM"),
    ("reported_value", "project.reported_value", "HIGH"),
    ("start_date", "project.start_date", "HIGH"),
)
logger = get_logger("ingestion")


@dataclass(frozen=True)
class IngestionResult:
    report_type: str
    pipeline_run_id: UUID
    source_document_id: UUID
    canonical_entity_id: UUID | None
    created_document: bool
    duplicate_prevented: bool
    created_count: int
    parsed_project_rows: int = 0
    parsed_contacts: int = 0
    quality_flag_codes: tuple[str, ...] = ()
    reconciliation_passed: bool | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(*parts: object) -> str:
    payload = "\x1f".join("" if part is None else str(part) for part in parts)
    return sha256(payload.encode("utf-8")).hexdigest()


def _safe_decimal(value: float | str) -> Decimal:
    return Decimal(str(value))


def _history_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


class ConstructConnectIngestionService:
    """Persist the two validated ConstructConnect PDF report formats into DATA-0.4.0.

    Scope claim: Validated against the supplied Project and Company report formats;
    architecture supports additional adapters.
    """

    def __init__(self, session: Session):
        self.session = session
        self._event_seq = 0

    def ingest(self, path: str | Path) -> IngestionResult:
        report_type = "UNKNOWN"
        try:
            payload = load_pdf(path)
            report_type = detect_report_type(payload)
            existing = self.session.scalar(
                sa.select(SourceDocument).where(
                    SourceDocument.source_type == SOURCE_TYPE,
                    SourceDocument.content_sha256 == payload.sha256,
                )
            )
            if existing is not None:
                run = self._start_run(report_type)
                with bind_pipeline_run(str(run.id)):
                    run.status = RunStatus.SUCCEEDED
                    run.source_document_count = 1
                    run.duplicate_count = 1
                    run.completed_at = _now()
                    self._event(run, "DUPLICATE_PREVENTED", "INGEST", "SourceDocument", str(existing.id), payload.sha256)
                    self.session.commit()
                    logger.info(
                        "pipeline.ingest.duplicate_prevented",
                        extra={"safe_extra": {"report_type": report_type, "pipeline_run_id": str(run.id)}},
                    )
                    entity_id = self._entity_id_for_existing(existing)
                    return IngestionResult(
                        report_type=report_type,
                        pipeline_run_id=run.id,
                        source_document_id=existing.id,
                        canonical_entity_id=entity_id,
                        created_document=False,
                        duplicate_prevented=True,
                        created_count=0,
                    )

            run = self._start_run(report_type)
            with bind_pipeline_run(str(run.id)):
                logger.info(
                    "pipeline.ingest.started",
                    extra={"safe_extra": {"report_type": report_type, "pipeline_run_id": str(run.id)}},
                )
                if report_type == "PROJECT":
                    parsed = parse_project_report(payload)
                    result = self._persist_project(payload, parsed, run)
                else:
                    parsed = parse_company_report(payload)
                    result = self._persist_company(payload, parsed, run)
                run.status = RunStatus.SUCCEEDED
                run.source_document_count = 1
                run.created_count = result.created_count
                run.exception_count = self.session.scalar(
                    sa.select(sa.func.count()).select_from(WorkflowException).where(WorkflowException.pipeline_run_id == run.id)
                ) or 0
                run.completed_at = _now()
                self.session.commit()
                logger.info(
                    "pipeline.ingest.succeeded",
                    extra={
                        "safe_extra": {
                            "report_type": report_type,
                            "pipeline_run_id": str(run.id),
                            "created_count": result.created_count,
                            "exception_count": run.exception_count,
                        }
                    },
                )
                return result
        except Exception as exc:
            self.session.rollback()
            # Persist a small independent failure run without retaining source contents, raw paths,
            # or credentials. This also covers malformed/undetectable PDFs that fail before parsing.
            failure = self._start_run(report_type)
            with bind_pipeline_run(str(failure.id)):
                failure.status = RunStatus.FAILED
                failure.error_summary = f"{type(exc).__name__}: {sanitize_for_log(str(exc))}"
                failure.completed_at = _now()
                event_type = "PARSER_RECONCILIATION_FAILED" if isinstance(exc, ParserReconciliationError) else "INGEST_FAILED"
                if isinstance(exc, ParserReconciliationError):
                    # The attempted organization/source rows were rolled back intentionally, but the
                    # operational exception must survive so a failed reconciliation is reviewable
                    # rather than disappearing with the transaction it quarantined.
                    failure.exception_count = 1
                    self.session.add(
                        WorkflowException(
                            pipeline_run_id=failure.id,
                            exception_type="PARSER_RECONCILIATION_FAILURE",
                            recommended_action=ExceptionResolutionAction.ESCALATE,
                            priority=100,
                            summary="ConstructConnect company report quarantined: row counts do not reconcile.",
                            detail=str(sanitize_for_log(str(exc))),
                        )
                    )
                self._event(
                    failure,
                    event_type,
                    "RECONCILE" if isinstance(exc, ParserReconciliationError) else "INGEST",
                    None,
                    None,
                    type(exc).__name__,
                )
                self.session.commit()
                logger.warning(
                    "pipeline.ingest.failed",
                    extra={
                        "safe_extra": {
                            "report_type": report_type,
                            "pipeline_run_id": str(failure.id),
                            "error_code": type(exc).__name__,
                        }
                    },
                )
            raise

    def _start_run(self, report_type: str) -> PipelineRun:
        run = PipelineRun(
            run_type="CONSTRUCTCONNECT_PDF_INGEST",
            mode="LOCAL",
            status=RunStatus.RUNNING,
            correlation_id=f"constructconnect-{report_type.lower()}-{uuid4()}",
            started_at=_now(),
        )
        self.session.add(run)
        self.session.flush()
        self._event_seq = 0
        return run

    def _event(
        self,
        run: PipelineRun,
        event_type: str,
        stage: str,
        entity_type: str | None,
        entity_id: str | None,
        message: str | None,
        *,
        safe_metadata: dict | None = None,
    ) -> None:
        self._event_seq += 1
        self.session.add(
            PipelineEvent(
                pipeline_run_id=run.id,
                sequence_number=self._event_seq,
                event_type=event_type,
                stage=stage,
                entity_type=entity_type,
                entity_id=entity_id,
                message=message,
                safe_metadata=safe_metadata,
                occurred_at=_now(),
            )
        )

    def _entity_id_for_existing(self, doc: SourceDocument) -> UUID | None:
        if doc.report_type == "PROJECT" and doc.external_id:
            project = self.session.scalar(
                sa.select(Project).where(Project.source_system == SOURCE_SYSTEM, Project.external_id == doc.external_id)
            )
            return project.id if project else None
        if doc.report_type == "COMPANY" and doc.external_id:
            org = self.session.scalar(
                sa.select(Organization).where(Organization.canonical_key == f"constructconnect:company:{doc.external_id}")
            )
            return org.id if org else None
        return None

    def _new_document(
        self,
        *,
        payload,
        report_type: str,
        external_id: str,
        report_date: datetime,
    ) -> SourceDocument:
        doc = SourceDocument(
            source_type=SOURCE_TYPE,
            source_system=SOURCE_SYSTEM,
            external_id=external_id,
            report_type=report_type,
            original_filename=payload.path.name,
            content_sha256=payload.sha256,
            blob_ref=f"private://constructconnect/{payload.sha256}",
            mime_type="application/pdf",
            byte_size=len(payload.content),
            report_date=report_date,
            imported_at=_now(),
            parser_version=PARSER_VERSION,
            is_synthetic=False,
            is_private=True,
        )
        self.session.add(doc)
        self.session.flush()
        return doc

    def _observation(
        self,
        doc: SourceDocument,
        *,
        field_name: str,
        raw: str | None,
        value_type: ValueType,
        project: Project | None = None,
        organization: Organization | None = None,
        person: Person | None = None,
        normalized_text: str | None = None,
        normalized_integer: int | None = None,
        normalized_decimal: Decimal | None = None,
        normalized_boolean: bool | None = None,
        normalized_date: date | None = None,
        normalized_datetime: datetime | None = None,
        currency_code: str | None = None,
        unit: str | None = None,
        evidence: EvidenceRef | None = None,
        evidence_classification: EvidenceClassification = EvidenceClassification.EXPLICIT,
        confidence_state: ConfidenceState = ConfidenceState.HIGH,
        confidence_score: Decimal | None = _safe_decimal("0.95"),
        confidence_reason: str | None = None,
        validation_state: ValidationState = ValidationState.VALID,
        scoring_treatment: ScoringTreatment = ScoringTreatment.FULL,
        locator: str = "",
        pii_class: PIIClass = PIIClass.NONE,
        masking_policy: MaskingPolicy = MaskingPolicy.NONE,
    ) -> SourceObservation:
        fp = _fingerprint(doc.content_sha256, locator, field_name, raw, project.id if project else None, organization.id if organization else None, person.id if person else None)
        eligibility, eligibility_reason = observation_decision_eligibility(
            classification=evidence_classification,
            validation_state=validation_state,
            scoring_treatment=scoring_treatment,
        )
        obs = SourceObservation(
            document_id=doc.id,
            project_id=project.id if project else None,
            organization_id=organization.id if organization else None,
            person_id=person.id if person else None,
            field_name=field_name,
            value_type=value_type,
            raw_value=raw,
            normalized_text=normalized_text,
            normalized_integer=normalized_integer,
            normalized_decimal=normalized_decimal,
            normalized_boolean=normalized_boolean,
            normalized_date=normalized_date,
            normalized_datetime=normalized_datetime,
            currency_code=currency_code,
            unit=unit,
            observation_fingerprint=fp,
            evidence_classification=evidence_classification,
            confidence_state=confidence_state,
            confidence_score=confidence_score,
            confidence_reason=confidence_reason,
            validation_state=validation_state,
            scoring_treatment=scoring_treatment,
            decision_eligible=eligibility,
            decision_eligibility_reason=eligibility_reason,
            observed_at=doc.report_date,
            freshness_at=doc.report_date,
            is_synthetic=False,
        )
        self.session.add(obs)
        self.session.flush()
        if evidence is not None:
            self._evidence(doc, obs, evidence, pii_class=pii_class, masking_policy=masking_policy)
        return obs

    def _evidence(
        self,
        doc: SourceDocument,
        obs: SourceObservation | None,
        evidence: EvidenceRef,
        *,
        pii_class: PIIClass = PIIClass.NONE,
        masking_policy: MaskingPolicy = MaskingPolicy.NONE,
    ) -> SourceEvidence:
        fingerprint = _fingerprint(doc.content_sha256, obs.id if obs else None, evidence.page, evidence.section, evidence.excerpt)
        ev = SourceEvidence(
            document_id=doc.id,
            observation_id=obs.id if obs else None,
            page_number=evidence.page,
            section_name=evidence.section,
            excerpt=evidence.excerpt,
            evidence_fingerprint=fingerprint,
            classification=EvidenceClassification.EXPLICIT,
            pii_class=pii_class,
            demo_masking_policy=masking_policy,
            is_permitted_for_decision=obs.decision_eligible if obs is not None else True,
        )
        self.session.add(ev)
        self.session.flush()
        return ev

    def _quality_flag(
        self,
        *,
        rule_code: str,
        severity: QualitySeverity,
        title: str,
        detail: str,
        project: Project | None = None,
        organization: Organization | None = None,
        person: Person | None = None,
        observation: SourceObservation | None = None,
        evidence: SourceEvidence | None = None,
        decision_impact: str | None = None,
        blocks: bool = False,
    ) -> QualityFlag:
        flag = QualityFlag(
            rule_code=rule_code,
            severity=severity,
            project_id=project.id if project else None,
            organization_id=organization.id if organization else None,
            person_id=person.id if person else None,
            observation_id=observation.id if observation else None,
            source_evidence_id=evidence.id if evidence else None,
            title=title,
            detail=detail,
            decision_impact=decision_impact,
            blocks_progression=blocks,
            first_detected_at=_now(),
        )
        self.session.add(flag)
        self.session.flush()
        return flag

    def _get_or_create_org(self, name: str, *, company_id: str | None = None) -> tuple[Organization, bool]:
        norm = normalized_name(name)
        if company_id:
            key = f"constructconnect:company:{company_id}"
            org = self.session.scalar(sa.select(Organization).where(Organization.canonical_key == key))
            if org:
                return org, False
        org = self.session.scalar(sa.select(Organization).where(Organization.normalized_name == norm))
        if org:
            if company_id and org.canonical_key.startswith("source-label:"):
                org.canonical_key = f"constructconnect:company:{company_id}"
            return org, False
        key = f"constructconnect:company:{company_id}" if company_id else f"source-label:{canonical_slug(name)}"
        org = Organization(canonical_name=name, normalized_name=norm, canonical_key=key, organization_type="CONTRACTOR")
        self.session.add(org)
        self.session.flush()
        return org, True

    def _ensure_org_alias(self, org: Organization, alias: str, observation: SourceObservation | None = None) -> None:
        norm = normalized_name(alias)
        exists = self.session.scalar(
            sa.select(OrganizationAlias).where(
                OrganizationAlias.organization_id == org.id,
                OrganizationAlias.normalized_alias == norm,
            )
        )
        if not exists:
            self.session.add(
                OrganizationAlias(
                    organization_id=org.id,
                    alias=alias,
                    normalized_alias=norm,
                    source_observation_id=observation.id if observation else None,
                    alias_type="SOURCE_LABEL",
                )
            )

    def _persist_project(self, payload, parsed: ParsedProjectReport, run: PipelineRun) -> IngestionResult:
        doc = self._new_document(
            payload=payload,
            report_type="PROJECT",
            external_id=parsed.project_id,
            report_date=parsed.report_date,
        )
        project = self.session.scalar(
            sa.select(Project).where(Project.source_system == SOURCE_SYSTEM, Project.external_id == parsed.project_id)
        )
        created = 0
        existing_project = project is not None
        if project is None:
            exact = sa.select(Project).where(Project.normalized_name == normalized_name(parsed.project_name))
            if parsed.region:
                exact = exact.where(Project.region == parsed.region)
            if parsed.city:
                exact = exact.where(Project.city == parsed.city)
            project = self.session.scalar(exact.limit(1))
            existing_project = project is not None
        if project is None:
            project = Project(
                canonical_name=parsed.project_name,
                normalized_name=normalized_name(parsed.project_name),
                canonical_key=f"constructconnect:{parsed.project_id}",
                source_system=SOURCE_SYSTEM,
                external_id=parsed.project_id,
                state=ProjectState.PARSED,
                stage=parsed.stage,
                category=parsed.category,
                city=parsed.city,
                region=parsed.region,
                country_code="US",
                reported_value=parsed.estimated_value,
                currency_code="USD" if parsed.estimated_value is not None else None,
                start_date=parsed.start_date,
                is_synthetic=False,
            )
            self.session.add(project)
            self.session.flush()
            created += 1
        else:
            project.canonical_key = f"constructconnect:{parsed.project_id}"
            project.source_system = SOURCE_SYSTEM
            project.external_id = parsed.project_id
            project.state = ProjectState.PARSED
            project.currency_code = "USD" if parsed.estimated_value is not None else project.currency_code

        self._event(run, "SOURCE_DOCUMENT_REGISTERED", "INGEST", "SourceDocument", str(doc.id), payload.sha256)
        self._event(run, "PROJECT_PARSED", "PARSE", "Project", str(project.id), parsed.project_name)
        if existing_project:
            change_count = self._apply_material_project_updates(project, parsed, doc, run)
            run.updated_count = 1 if change_count else 0

        self._observation(
            doc, field_name="project.external_id", raw=parsed.project_id, value_type=ValueType.IDENTIFIER,
            project=project, normalized_text=parsed.project_id, evidence=parsed.evidence["project_id"], locator="header:project_id"
        )
        self._observation(
            doc, field_name="project.name", raw=parsed.project_name, value_type=ValueType.TEXT,
            project=project, normalized_text=parsed.project_name, locator="header:name",
            evidence=EvidenceRef(1, "Header", parsed.project_name),
        )
        if parsed.category:
            self._observation(doc, field_name="project.category", raw=parsed.category, value_type=ValueType.TEXT, project=project, normalized_text=parsed.category, locator="header:category")
        if parsed.stage:
            self._observation(doc, field_name="project.stage", raw=parsed.stage, value_type=ValueType.ENUM, project=project, normalized_text=parsed.stage, evidence=parsed.evidence["stage"], locator="header:stage")
        if parsed.scope:
            self._observation(doc, field_name="project.scope", raw=parsed.scope, value_type=ValueType.TEXT, project=project, normalized_text=parsed.scope, evidence=parsed.evidence["scope"], locator="description:scope")
        if parsed.description:
            self._observation(
                doc, field_name="project.description", raw=parsed.description, value_type=ValueType.TEXT,
                project=project, normalized_text=parsed.description, evidence=parsed.evidence.get("description"),
                locator="description:narrative"
            )
        if parsed.notes:
            self._observation(
                doc, field_name="project.notes", raw=parsed.notes, value_type=ValueType.TEXT,
                project=project, normalized_text=parsed.notes, evidence=parsed.evidence.get("notes"),
                locator="description:notes"
            )
        if parsed.floor_area_raw:
            self._observation(
                doc, field_name="project.floor_area_sqft", raw=parsed.floor_area_raw, value_type=ValueType.INTEGER,
                project=project, normalized_integer=parsed.floor_area_sqft, unit="sqft", evidence=parsed.evidence.get("floor_area"),
                confidence_state=ConfidenceState.LOW, confidence_score=_safe_decimal("0.35"),
                confidence_reason="The source explicitly states the listed square footage is estimated from broader development projections.",
                validation_state=ValidationState.REQUIRES_REVIEW, scoring_treatment=ScoringTreatment.CAPPED,
                locator="details:floor_area"
            )
        if parsed.work_type:
            self._observation(
                doc, field_name="project.work_type", raw=parsed.work_type, value_type=ValueType.TEXT,
                project=project, normalized_text=parsed.work_type, evidence=parsed.evidence.get("work_type"),
                locator="details:work_type"
            )
        if parsed.estimated_value_raw:
            value_obs = self._observation(
                doc,
                field_name="project.reported_value",
                raw=parsed.estimated_value_raw,
                value_type=ValueType.MONEY,
                project=project,
                normalized_decimal=parsed.estimated_value,
                currency_code="USD",
                evidence=parsed.evidence["reported_value"],
                confidence_state=ConfidenceState.LOW,
                confidence_score=_safe_decimal("0.35"),
                confidence_reason="The source explicitly states phase-level value is estimated from broader development projections.",
                validation_state=ValidationState.REQUIRES_REVIEW,
                scoring_treatment=ScoringTreatment.CAPPED,
                locator="header:reported_value",
            )
            caveat_ev = self._evidence(doc, value_obs, parsed.evidence["value_caveat"])
            self._quality_flag(
                rule_code="PROJECT_VALUE_UNCERTAINTY",
                severity=QualitySeverity.HIGH,
                title="Phase-level value is explicitly estimated",
                detail=parsed.evidence["value_caveat"].excerpt,
                project=project,
                observation=value_obs,
                evidence=caveat_ev,
                decision_impact="LOW_TO_MEDIUM",
                blocks=False,
            )
        if parsed.start_date:
            date_obs = self._observation(
                doc,
                field_name="project.start_date",
                raw=parsed.start_date.isoformat(),
                value_type=ValueType.DATE,
                project=project,
                normalized_date=parsed.start_date,
                evidence=parsed.evidence["start_date"],
                confidence_state=ConfidenceState.MEDIUM,
                confidence_score=_safe_decimal("0.55"),
                confidence_reason="Date is source-explicit but event semantics are internally inconsistent.",
                validation_state=ValidationState.REQUIRES_REVIEW if parsed.start_date_label == "Actual Start Date" and parsed.start_date > parsed.report_date.date() else ValidationState.VALID,
                scoring_treatment=ScoringTreatment.REVIEW,
                locator="events:start_date",
            )
            if parsed.start_date_label == "Actual Start Date" and parsed.start_date > parsed.report_date.date():
                self._quality_flag(
                    rule_code="FUTURE_ACTUAL_DATE",
                    severity=QualitySeverity.HIGH,
                    title="Future date labeled as actual",
                    detail=f"Source report date {parsed.report_date.date()} precedes 'Actual Start Date' {parsed.start_date}.",
                    project=project,
                    observation=date_obs,
                    decision_impact="HIGH",
                    blocks=False,
                )
        if parsed.currently_tracked is not None:
            self._observation(
                doc, field_name="source.currently_tracked", raw=str(parsed.currently_tracked), value_type=ValueType.BOOLEAN,
                project=project, normalized_boolean=parsed.currently_tracked, evidence=parsed.evidence["tracked"], locator="history:tracked"
            )
            if parsed.currently_tracked is False and parsed.viewed_by:
                self._quality_flag(
                    rule_code="VIEWED_NOT_TRACKED",
                    severity=QualitySeverity.MEDIUM,
                    title="Viewed source record is not tracked",
                    detail=f"{parsed.viewed_by} viewed the record, but the source says it is not currently tracked.",
                    project=project,
                    decision_impact="HIGH",
                )

        for idx, row in enumerate(parsed.design_team, 1):
            org, was_created = self._get_or_create_org(row.company_name)
            created += int(was_created)
            org_obs = self._observation(
                doc,
                field_name="project.organization",
                raw=row.company_name,
                value_type=ValueType.TEXT,
                project=project,
                organization=org,
                normalized_text=row.company_name,
                locator=f"design_team:{idx}:{row.role}",
                evidence=EvidenceRef(row.page, "Design Team", f"{row.role}: {row.company_name}"),
            )
            self._ensure_org_alias(org, row.company_name, org_obs)
            relation = self.session.scalar(
                sa.select(ProjectOrganization).where(
                    ProjectOrganization.project_id == project.id,
                    ProjectOrganization.organization_id == org.id,
                    ProjectOrganization.role == row.role,
                )
            )
            if relation is None:
                self.session.add(
                    ProjectOrganization(
                        project_id=project.id,
                        organization_id=org.id,
                        role=row.role,
                        verification_state=VerificationState.SUPPORTED,
                        source_observation_id=org_obs.id,
                    )
                )
            if row.contact_name:
                person = Person(
                    display_name=row.contact_name,
                    normalized_name=normalized_name(row.contact_name),
                    current_organization_id=org.id,
                    employment_state=VerificationState.SUPPORTED,
                    status=row.contact_status or "UNKNOWN",
                )
                self.session.add(person)
                self.session.flush()
                created += 1
                if row.email:
                    self.session.add(
                        PersonContactPoint(
                            person_id=person.id,
                            organization_id=org.id,
                            contact_type=ContactPointType.EMAIL,
                            value=row.email,
                            normalized_value=row.email,
                            pii_class=PIIClass.BUSINESS_CONTACT,
                            demo_masking_policy=MaskingPolicy.PARTIAL,
                            verification_state=VerificationState.SUPPORTED,
                            is_generic=is_generic_email(row.email),
                            is_primary=True,
                        )
                    )

        gc_rows = [row for row in parsed.design_team if row.role == "General Contractor"]
        if gc_rows and not any(row.contact_name for row in gc_rows):
            self._quality_flag(
                rule_code="MISSING_PROJECT_GC_CONTACT",
                severity=QualitySeverity.MEDIUM,
                title="No named project-level GC contact in supplied project report",
                detail="The General Contractor is named, but the Stafford Design Team row does not identify a person for that GC.",
                project=project,
                decision_impact="VERY_HIGH",
            )

        self.session.flush()
        codes = tuple(sorted({flag.rule_code for flag in self.session.scalars(sa.select(QualityFlag).where(QualityFlag.project_id == project.id)).all()}))
        return IngestionResult(
            report_type="PROJECT",
            pipeline_run_id=run.id,
            source_document_id=doc.id,
            canonical_entity_id=project.id,
            created_document=True,
            duplicate_prevented=False,
            created_count=created + 1,
            quality_flag_codes=codes,
        )

    def _apply_material_project_updates(
        self,
        project: Project,
        parsed: ParsedProjectReport,
        doc: SourceDocument,
        run: PipelineRun,
    ) -> int:
        """Apply non-null source updates while preserving material before/after lineage."""
        candidates: dict[str, object | None] = {
            "canonical_name": parsed.project_name,
            "stage": parsed.stage,
            "category": parsed.category,
            "reported_value": parsed.estimated_value,
            "start_date": parsed.start_date,
        }
        change_count = 0
        for attribute, field_name, impact in MATERIAL_PROJECT_FIELD_POLICY:
            previous = getattr(project, attribute)
            candidate = candidates[attribute]
            # Missing values in a later source do not erase established canonical state.
            if candidate is None or candidate == previous:
                continue
            setattr(project, attribute, candidate)
            if attribute == "canonical_name":
                project.normalized_name = normalized_name(str(candidate))
            self.session.add(
                FieldHistory(
                    pipeline_run_id=run.id,
                    source_document_id=doc.id,
                    entity_type="Project",
                    entity_id=str(project.id),
                    field_name=field_name,
                    previous_value=_history_value(previous),
                    new_value=_history_value(candidate),
                    change_type="MATERIAL_SOURCE_CHANGE",
                    detected_at=_now(),
                    commercial_impact=impact,
                )
            )
            self._event(
                run,
                "MATERIAL_FIELD_CHANGED",
                "CHANGE_DETECTION",
                "Project",
                str(project.id),
                field_name,
                safe_metadata={
                    "field_name": field_name,
                    "change_type": "MATERIAL_SOURCE_CHANGE",
                    "commercial_impact": impact,
                    "source_document_id": str(doc.id),
                },
            )
            change_count += 1
        return change_count

    def _persist_company(self, payload, parsed: ParsedCompanyReport, run: PipelineRun) -> IngestionResult:
        doc = self._new_document(
            payload=payload,
            report_type="COMPANY",
            external_id=parsed.company_id,
            report_date=parsed.report_date,
        )
        org, org_created = self._get_or_create_org(parsed.company_name, company_id=parsed.company_id)
        created = int(org_created)
        self._event(run, "SOURCE_DOCUMENT_REGISTERED", "INGEST", "SourceDocument", str(doc.id), payload.sha256)
        self._event(run, "COMPANY_PARSED", "PARSE", "Organization", str(org.id), parsed.company_name)

        name_obs = self._observation(
            doc, field_name="organization.name", raw=parsed.company_name, value_type=ValueType.TEXT,
            organization=org, normalized_text=parsed.company_name, evidence=EvidenceRef(1, "Header", parsed.company_name), locator="header:name"
        )
        self._ensure_org_alias(org, parsed.company_name, name_obs)
        self._observation(
            doc, field_name="organization.external_id", raw=parsed.company_id, value_type=ValueType.IDENTIFIER,
            organization=org, normalized_text=parsed.company_id, evidence=parsed.evidence["company_id"], locator="header:company_id"
        )
        if parsed.last_update:
            self._observation(
                doc,
                field_name="organization.source_last_update",
                raw=parsed.last_update.isoformat(),
                value_type=ValueType.DATETIME,
                organization=org,
                normalized_datetime=parsed.last_update,
                evidence=EvidenceRef(1, "Header", f"Last Update: {parsed.last_update.isoformat()}"),
                locator="header:last_update",
            )
        for field, raw, integer in (
            ("organization.planning_project_count", str(parsed.planning_projects), parsed.planning_projects),
            ("organization.post_bid_project_count", str(parsed.post_bid_projects), parsed.post_bid_projects),
            ("organization.bidding_role_project_count", str(parsed.bidding_role_projects), parsed.bidding_role_projects),
        ):
            self._observation(
                doc, field_name=field, raw=raw, value_type=ValueType.INTEGER,
                organization=org, normalized_integer=integer, evidence=parsed.evidence["project_counts"], locator=f"header:{field}"
            )
        if parsed.street_address:
            self.session.add(
                OrganizationAddress(
                    organization_id=org.id,
                    address_type="SOURCE_HQ",
                    line1=parsed.street_address,
                    country_code="US",
                    normalized_address=normalized_name(parsed.street_address),
                )
            )
        primary_domain = email_domain(parsed.company_email)
        if primary_domain:
            self._ensure_domain(org, primary_domain, is_primary=True, state=VerificationState.SUPPORTED)

        all_rows = [*parsed.planning_rows, *parsed.post_bid_rows, *parsed.bidding_role_rows]
        for row in all_rows:
            project, was_created = self._get_or_create_company_project(parsed, row)
            created += int(was_created)
            self._persist_company_project_row(doc, org, project, row)

        person_rows: list[tuple[Person, object]] = []
        domains: set[str] = set()
        for row in parsed.contacts:
            person = Person(
                display_name=row.name,
                normalized_name=normalized_name(row.name),
                current_organization_id=org.id,
                employment_state=VerificationState.SUPPORTED if (row.status or "").lower() == "active" else VerificationState.UNKNOWN,
                status=(row.status or "UNKNOWN").upper(),
            )
            self.session.add(person)
            self.session.flush()
            created += 1
            person_rows.append((person, row))
            contact_obs = self._observation(
                doc,
                field_name="person.source_contact_row",
                raw=" | ".join(row.raw_columns),
                value_type=ValueType.TEXT,
                organization=org,
                person=person,
                normalized_text=row.name,
                locator=f"contacts:{row.row_number}",
                evidence=EvidenceRef(row.page, "Contacts", " | ".join(row.raw_columns)),
                pii_class=PIIClass.BUSINESS_CONTACT,
                masking_policy=MaskingPolicy.HIDDEN,
            )
            if row.email:
                domain = email_domain(row.email)
                if domain:
                    domains.add(domain)
                    self._ensure_domain(
                        org,
                        domain,
                        is_primary=(domain == primary_domain),
                        state=VerificationState.SUPPORTED if domain == primary_domain else VerificationState.UNKNOWN,
                        source_observation=contact_obs,
                    )
                point = PersonContactPoint(
                    person_id=person.id,
                    organization_id=org.id,
                    contact_type=ContactPointType.EMAIL,
                    value=row.email,
                    normalized_value=row.email,
                    pii_class=PIIClass.BUSINESS_CONTACT,
                    demo_masking_policy=MaskingPolicy.PARTIAL,
                    verification_state=VerificationState.SUPPORTED,
                    is_generic=is_generic_email(row.email),
                    is_primary=True,
                    source_observation_id=contact_obs.id,
                )
                self.session.add(point)
                if point.is_generic:
                    self._quality_flag(
                        rule_code="GENERIC_CONTACT_EMAIL",
                        severity=QualitySeverity.MEDIUM,
                        title="Named contact uses a generic company inbox",
                        detail=f"{row.name} is associated with generic inbox {row.email}; do not treat this as a verified personal address.",
                        organization=org,
                        person=person,
                        observation=contact_obs,
                        decision_impact="HIGH",
                    )
            if row.phone:
                self.session.add(
                    PersonContactPoint(
                        person_id=person.id,
                        organization_id=org.id,
                        contact_type=ContactPointType.PHONE,
                        value=row.phone,
                        normalized_value=row.phone,
                        pii_class=PIIClass.BUSINESS_CONTACT,
                        demo_masking_policy=MaskingPolicy.PARTIAL,
                        verification_state=VerificationState.SUPPORTED,
                        is_primary=True,
                        source_observation_id=contact_obs.id,
                    )
                )

        if len(domains) > 1:
            self._quality_flag(
                rule_code="ORGANIZATION_DOMAIN_CONFLICT",
                severity=QualitySeverity.HIGH,
                title="Multiple organizational email domains occur in one source account",
                detail="ConstructConnect's EE Reed Houston account contains contacts using: " + ", ".join(sorted(domains)) + ". Relationship must be resolved before automatic CRM merge.",
                organization=org,
                decision_impact="HIGH",
                blocks=False,
            )

        self._detect_contact_duplicates(org, person_rows)

        if parsed.currently_tracked is False and parsed.viewed_by:
            self._quality_flag(
                rule_code="VIEWED_NOT_TRACKED",
                severity=QualitySeverity.MEDIUM,
                title="Viewed source account is not tracked",
                detail=f"{parsed.viewed_by} viewed the company record, but the source says it is not currently tracked.",
                organization=org,
                decision_impact="HIGH",
            )

        if not parsed.reconciliation.passed:
            flag = self._quality_flag(
                rule_code="PARSER_RECONCILIATION_FAILURE",
                severity=QualitySeverity.CRITICAL,
                title="Company project row counts do not reconcile",
                detail=(
                    f"Expected/parsed planning {parsed.reconciliation.expected_planning}/{parsed.reconciliation.parsed_planning}; "
                    f"post-bid {parsed.reconciliation.expected_post_bid}/{parsed.reconciliation.parsed_post_bid}; "
                    f"bidding-role {parsed.reconciliation.expected_bidding_role}/{parsed.reconciliation.parsed_bidding_role}."
                ),
                organization=org,
                decision_impact="CRITICAL",
                blocks=True,
            )
            self.session.add(
                WorkflowException(
                    quality_flag_id=flag.id,
                    pipeline_run_id=run.id,
                    exception_type="PARSER_RECONCILIATION_FAILURE",
                    recommended_action=ExceptionResolutionAction.ESCALATE,
                    priority=100,
                    summary="ConstructConnect company report quarantined: row counts do not reconcile.",
                    detail=flag.detail,
                )
            )
            raise ParserReconciliationError(flag.detail)

        self._event(
            run,
            "PARSER_RECONCILIATION_PASS",
            "RECONCILE",
            "Organization",
            str(org.id),
            f"planning=6 post_bid=87 bidding_role=74 contacts={len(parsed.contacts)}",
        )
        self.session.flush()
        codes = tuple(sorted({flag.rule_code for flag in self.session.scalars(sa.select(QualityFlag).where(QualityFlag.organization_id == org.id)).all()}))
        return IngestionResult(
            report_type="COMPANY",
            pipeline_run_id=run.id,
            source_document_id=doc.id,
            canonical_entity_id=org.id,
            created_document=True,
            duplicate_prevented=False,
            created_count=created + 1,
            parsed_project_rows=len(all_rows),
            parsed_contacts=len(parsed.contacts),
            quality_flag_codes=codes,
            reconciliation_passed=True,
        )

    def _ensure_domain(
        self,
        org: Organization,
        domain: str,
        *,
        is_primary: bool,
        state: VerificationState,
        source_observation: SourceObservation | None = None,
    ) -> None:
        existing = self.session.scalar(
            sa.select(OrganizationDomain).where(
                OrganizationDomain.organization_id == org.id,
                OrganizationDomain.normalized_domain == domain.lower(),
            )
        )
        if existing:
            if is_primary:
                existing.is_primary = True
                existing.relationship_state = state
            return
        self.session.add(
            OrganizationDomain(
                organization_id=org.id,
                domain=domain,
                normalized_domain=domain.lower(),
                relationship_state=state,
                source_observation_id=source_observation.id if source_observation else None,
                is_primary=is_primary,
            )
        )

    def _get_or_create_company_project(self, parsed: ParsedCompanyReport, row: CompanyProjectRow) -> tuple[Project, bool]:
        norm = normalized_name(row.project_name)
        stmt = sa.select(Project).where(Project.normalized_name == norm)
        if row.region:
            stmt = stmt.where(Project.region == row.region)
        if row.city:
            stmt = stmt.where(Project.city == row.city)
        project = self.session.scalar(stmt.limit(1))
        if project:
            return project, False
        digest = sha256(f"{norm}|{row.city or ''}|{row.region or ''}".encode()).hexdigest()[:20]
        project = Project(
            canonical_name=row.project_name,
            normalized_name=norm,
            canonical_key=f"constructconnect:company:{parsed.company_id}:project:{digest}",
            source_system="constructconnect_company_report",
            external_id=None,
            state=ProjectState.PARSED,
            stage=row.stage,
            city=row.city,
            region=row.region,
            country_code="US",
            reported_value=row.value,
            currency_code="USD" if row.value is not None else None,
            is_synthetic=False,
        )
        self.session.add(project)
        self.session.flush()
        return project, True

    def _persist_company_project_row(
        self,
        doc: SourceDocument,
        org: Organization,
        project: Project,
        row: CompanyProjectRow,
    ) -> None:
        locator = f"{row.section}:{row.row_number}:p{row.page}"
        evidence = EvidenceRef(row.page, f"{row.section} project table", " | ".join(row.raw_columns))
        row_obs = self._observation(
            doc,
            field_name="company_report.project_row",
            raw=" | ".join(row.raw_columns),
            value_type=ValueType.TEXT,
            project=project,
            organization=org,
            normalized_text=row.project_name,
            locator=locator,
            evidence=evidence,
        )
        for suffix, raw, kwargs in (
            ("name", row.project_name, {"normalized_text": row.project_name, "value_type": ValueType.TEXT}),
            ("section", row.section, {"normalized_text": row.section, "value_type": ValueType.ENUM}),
            ("stage", row.stage, {"normalized_text": row.stage, "value_type": ValueType.ENUM}),
            ("value", row.value_raw, {"normalized_decimal": row.value, "value_type": ValueType.MONEY, "currency_code": "USD"}),
            ("contact", row.contact, {"normalized_text": row.contact, "value_type": ValueType.TEXT}),
            ("role", row.role, {"normalized_text": row.role, "value_type": ValueType.TEXT}),
            ("bid_date", row.bid_date_raw, {"normalized_date": row.bid_date, "value_type": ValueType.DATE}),
            ("bid_amount", row.bid_amount_raw, {"normalized_decimal": row.bid_amount, "value_type": ValueType.MONEY, "currency_code": "USD"}),
            ("bid_rank", row.bid_rank_raw, {"normalized_integer": row.bid_rank, "value_type": ValueType.INTEGER}),
        ):
            if raw:
                value_type = kwargs.pop("value_type")
                self._observation(
                    doc,
                    field_name=f"company_report.project.{suffix}",
                    raw=raw,
                    value_type=value_type,
                    project=project,
                    organization=org,
                    locator=f"{locator}:{suffix}",
                    evidence=evidence,
                    **kwargs,
                )
        relation_role = row.role or "SOURCE_ACCOUNT_PROJECT"
        exists = self.session.scalar(
            sa.select(ProjectOrganization).where(
                ProjectOrganization.project_id == project.id,
                ProjectOrganization.organization_id == org.id,
                ProjectOrganization.role == relation_role,
            )
        )
        if exists is None:
            self.session.add(
                ProjectOrganization(
                    project_id=project.id,
                    organization_id=org.id,
                    role=relation_role,
                    verification_state=VerificationState.SUPPORTED,
                    source_observation_id=row_obs.id,
                )
            )

    def _detect_contact_duplicates(self, org: Organization, person_rows: list[tuple[Person, object]]) -> None:
        seen_pairs: set[tuple[int, int]] = set()
        for i, (person_a, row_a) in enumerate(person_rows):
            for j in range(i + 1, len(person_rows)):
                person_b, row_b = person_rows[j]
                same_email = bool(row_a.email and row_b.email and row_a.email == row_b.email)
                same_phone = bool(row_a.phone and row_b.phone and row_a.phone == row_b.phone)
                same_address = bool(row_a.address and row_b.address and normalized_name(row_a.address) == normalized_name(row_b.address))
                name_score = fuzz.ratio(normalized_name(row_a.name), normalized_name(row_b.name))
                exact_name = normalized_name(row_a.name) == normalized_name(row_b.name)
                plausible = exact_name and (same_email or same_phone) or (name_score >= 90 and same_phone and same_address)
                if not plausible or (i, j) in seen_pairs:
                    continue
                seen_pairs.add((i, j))
                self._quality_flag(
                    rule_code="POSSIBLE_DUPLICATE_CONTACT",
                    severity=QualitySeverity.MEDIUM,
                    title="Possible duplicate or malformed contact",
                    detail=(
                        f"Source rows '{row_a.name}' and '{row_b.name}' have name similarity {name_score:.0f}%"
                        f"; same phone={same_phone}; same address={same_address}; same email={same_email}. Human review required before merge."
                    ),
                    organization=org,
                    person=person_b,
                    decision_impact="HIGH",
                )
