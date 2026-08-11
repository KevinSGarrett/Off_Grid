from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.crm.config import CRMIntegrationConfig, load_crm_integration_config
from app.crm.types import (
    CRMReadinessResult,
    FormsPreview,
    IntegrationRequest,
    PipedrivePreview,
    ReadinessCheck,
    SheetsPreview,
    TrelloPreview,
    Wave10IntegrationResult,
)
from app.domain.states import (
    ActionStatus,
    CRMPromotionState,
    CRMObjectType,
    ContactState,
    IntegrationMode,
    MotionStatus,
    MotionType,
    SyncStatus,
    VerificationState,
    CommercialOutcomeType,
)
from app.integrations.google_workspace import GoogleWorkspaceAdapter
from app.integrations.pipedrive import PipedriveAdapter
from app.integrations.trello import TrelloAdapter
from app.models import (
    AuditEvent,
    CommercialMotion,
    CommercialOutcome,
    ContactAssessment,
    ContactCandidate,
    CRMRecord,
    CRMSyncAttempt,
    NextAction,
    OpportunityAssessment,
    Organization,
    Person,
    Project,
)


class Wave10IntegrationService:
    """Build safe integration contracts and dry-run state from real canonical application data."""

    def __init__(
        self,
        session: Session,
        *,
        config: CRMIntegrationConfig | None = None,
        demo_mode: bool = True,
        pipedrive_mode: IntegrationMode = IntegrationMode.DRY_RUN,
        google_mode: IntegrationMode = IntegrationMode.OFF,
        trello_mode: IntegrationMode = IntegrationMode.OFF,
    ) -> None:
        self.session = session
        self.config = config or load_crm_integration_config()
        self.crm_cfg = self.config.crm
        self.reporting_cfg = self.config.reporting
        self.demo_mode = demo_mode
        self.pipedrive_mode = pipedrive_mode
        self.google_mode = google_mode
        self.trello_mode = trello_mode

    def run(self, project_external_id: str = "1007341663") -> Wave10IntegrationResult:
        project = self.session.scalar(
            sa.select(Project).where(Project.external_id == project_external_id)
        )
        if project is None:
            raise ValueError(f"Project {project_external_id!r} not found")
        readiness = self._readiness(project)
        pipedrive = self._pipedrive_preview(project, readiness)
        sheets = self._sheets_preview(project, readiness)
        forms = self._forms_preview()
        trello = self._trello_preview(project)
        self.session.commit()
        return Wave10IntegrationResult(
            crm_version=self.config.version,
            reporting_version=self.config.reporting_version,
            project_id=project.id,
            readiness=readiness,
            pipedrive=pipedrive,
            sheets=sheets,
            forms=forms,
            trello=trello,
            crm_record_count=self.session.scalar(
                sa.select(sa.func.count()).select_from(CRMRecord).where(CRMRecord.project_id == project.id)
            ) or 0,
            crm_sync_attempt_count=self.session.scalar(
                sa.select(sa.func.count())
                .select_from(CRMSyncAttempt)
                .join(CRMRecord, CRMSyncAttempt.crm_record_id == CRMRecord.id)
                .where(CRMRecord.project_id == project.id)
            ) or 0,
            audit_event_count=self.session.scalar(
                sa.select(sa.func.count()).select_from(AuditEvent).where(
                    AuditEvent.object_type == "PROJECT", AuditEvent.object_id == str(project.id)
                )
            ) or 0,
            external_writes_executed=0,
        )

    def _assessment(self, project_id: UUID) -> OpportunityAssessment:
        row = self.session.scalar(
            sa.select(OpportunityAssessment)
            .where(OpportunityAssessment.project_id == project_id, OpportunityAssessment.is_current.is_(True))
            .order_by(OpportunityAssessment.computed_at.desc())
        )
        if row is None:
            raise ValueError("Current opportunity assessment required before CRM readiness")
        return row

    def _contractor_motion(self, project_id: UUID) -> CommercialMotion | None:
        return self.session.scalar(
            sa.select(CommercialMotion).where(
                CommercialMotion.project_id == project_id,
                CommercialMotion.motion_type == MotionType.CONTRACTOR,
            )
        )

    def _rental_motion(self, project_id: UUID) -> CommercialMotion | None:
        return self.session.scalar(
            sa.select(CommercialMotion).where(
                CommercialMotion.project_id == project_id,
                CommercialMotion.motion_type == MotionType.RENTAL_HOUSE,
            )
        )

    def _best_contact(self, project_id: UUID) -> tuple[ContactCandidate | None, ContactAssessment | None, Person | None]:
        candidate = self.session.scalar(
            sa.select(ContactCandidate)
            .where(ContactCandidate.project_id == project_id, ContactCandidate.is_current.is_(True))
            .order_by(ContactCandidate.rank.asc().nulls_last(), ContactCandidate.candidate_score.desc())
        )
        if candidate is None:
            return None, None, None
        assessment = self.session.scalar(
            sa.select(ContactAssessment)
            .where(ContactAssessment.candidate_id == candidate.id, ContactAssessment.is_current.is_(True))
            .order_by(ContactAssessment.assessed_at.desc())
        )
        return candidate, assessment, self.session.get(Person, candidate.person_id)

    def _readiness(self, project: Project) -> CRMReadinessResult:
        assessment = self._assessment(project.id)
        contractor = self._contractor_motion(project.id)
        rental = self._rental_motion(project.id)
        candidate, contact_assessment, _person = self._best_contact(project.id)
        minimum = Decimal(str(self.crm_cfg["readiness"]["minimum_data_confidence_for_lead"]))

        lead_checks = [
            ReadinessCheck(
                key="qualified_project",
                passed=assessment.disposition == "PURSUE",
                applies_to=(CRMPromotionState.LEAD, CRMPromotionState.DEAL),
                rationale=f"Current deterministic disposition is {assessment.disposition}.",
            ),
            ReadinessCheck(
                key="canonical_project_identifier",
                passed=bool(project.external_id and project.canonical_key),
                applies_to=(CRMPromotionState.LEAD, CRMPromotionState.DEAL),
                rationale="ConstructConnect external ID and canonical project key support deterministic deduplication.",
            ),
            ReadinessCheck(
                key="source_backed_general_contractor",
                passed=bool(contractor and contractor.organization_id),
                applies_to=(CRMPromotionState.LEAD, CRMPromotionState.DEAL),
                rationale="A canonical contractor-side organization must exist before a Lead is created.",
            ),
            ReadinessCheck(
                key="data_confidence_threshold",
                passed=Decimal(assessment.data_confidence_score) >= minimum,
                applies_to=(CRMPromotionState.LEAD, CRMPromotionState.DEAL),
                rationale=(
                    f"Current data confidence {Decimal(assessment.data_confidence_score):.2f} "
                    f"is compared with configured Lead floor {minimum:.2f}."
                ),
            ),
            ReadinessCheck(
                key="deterministic_dedupe_key",
                passed=bool(project.external_id),
                applies_to=(CRMPromotionState.LEAD, CRMPromotionState.DEAL),
                rationale=f"Project dedupe key is constructconnect:{project.external_id}.",
            ),
        ]
        authority_verified = bool(
            contact_assessment and contact_assessment.rental_authority_state is VerificationState.VERIFIED
        )
        need_action = self.session.scalar(
            sa.select(NextAction).where(
                NextAction.project_id == project.id,
                NextAction.action_type == "VALIDATE_TEMP_LIGHTING_POWER_NEED",
            )
        )
        site_need_verified = bool(need_action and need_action.status is ActionStatus.COMPLETE)
        rental_provider_resolved = bool(rental and rental.organization_id and rental.status not in {MotionStatus.UNRESOLVED, MotionStatus.DISCOVERY})
        branch_action = self.session.scalar(
            sa.select(NextAction).where(
                NextAction.project_id == project.id,
                NextAction.action_type == "RESOLVE_RENTAL_BRANCH_FLEET_BUYER",
            )
        )
        branch_or_buyer_resolved = bool(branch_action and branch_action.status is ActionStatus.COMPLETE)
        deal_checks = [
            ReadinessCheck(
                key="rental_authority_verified",
                passed=authority_verified,
                applies_to=(CRMPromotionState.DEAL,),
                rationale="A ranked/relevant contact is not equivalent to verified equipment/rental authority.",
            ),
            ReadinessCheck(
                key="site_need_verified",
                passed=site_need_verified,
                applies_to=(CRMPromotionState.DEAL,),
                rationale="Product-fit inference must be converted into a verified current/upcoming site need.",
            ),
            ReadinessCheck(
                key="rental_provider_resolved",
                passed=rental_provider_resolved,
                applies_to=(CRMPromotionState.DEAL,),
                rationale="The serving rental provider remains unresolved in the current Stafford evidence.",
            ),
            ReadinessCheck(
                key="rental_branch_or_fleet_buyer_resolved",
                passed=branch_or_buyer_resolved,
                applies_to=(CRMPromotionState.DEAL,),
                rationale="The supply/channel decision path must be resolved before Deal promotion.",
            ),
        ]
        checks = tuple(lead_checks + deal_checks)
        lead_blockers = tuple(c.key for c in lead_checks if not c.passed)
        deal_blockers = tuple(c.key for c in checks if not c.passed)
        lead_ready = not lead_blockers
        deal_ready = not deal_blockers
        permitted = (
            CRMPromotionState.DEAL
            if deal_ready
            else CRMPromotionState.LEAD
            if lead_ready
            else CRMPromotionState.INTELLIGENCE
        )
        return CRMReadinessResult(
            version=self.config.version,
            project_id=project.id,
            project_external_id=project.external_id or "",
            commercial_fit=Decimal(assessment.commercial_fit_score),
            data_confidence=Decimal(assessment.data_confidence_score),
            lead_ready=lead_ready,
            deal_ready=deal_ready,
            permitted_promotion=permitted,
            checks=checks,
            lead_blockers=lead_blockers,
            deal_blockers=deal_blockers,
        )

    def _organization(self, project_id: UUID) -> Organization:
        motion = self._contractor_motion(project_id)
        if motion is None or motion.organization_id is None:
            raise ValueError("Contractor organization missing")
        org = self.session.get(Organization, motion.organization_id)
        if org is None:
            raise ValueError("Contractor organization record missing")
        return org

    def _pipedrive_preview(self, project: Project, readiness: CRMReadinessResult) -> PipedrivePreview:
        org = self._organization(project.id)
        candidate, contact_assessment, person = self._best_contact(project.id)
        ep = self.crm_cfg["pipedrive"]["endpoints"]
        org_key = f"organization:{org.canonical_key}"
        lead_key = f"pipedrive:lead:constructconnect:{project.external_id}"
        deal_key = f"pipedrive:deal:constructconnect:{project.external_id}"

        org_req = IntegrationRequest(
            object_type=CRMObjectType.ORGANIZATION,
            label="Create or resolve canonical organization",
            method=ep["organization_create"]["method"],
            path=ep["organization_create"]["path"],
            body={"name": org.canonical_name},
            canonical_key=org_key,
        )
        person_req: IntegrationRequest | None = None
        if candidate and person and contact_assessment:
            safe_to_map = (
                candidate.state in {ContactState.PROJECT_ASSOCIATION_VERIFIED, ContactState.ROLE_RELEVANT, ContactState.AUTHORITY_VERIFIED}
                and contact_assessment.employment_state is VerificationState.VERIFIED
                and contact_assessment.project_association_state is VerificationState.VERIFIED
                and candidate.organization_id == org.id
            )
            person_req = IntegrationRequest(
                object_type=CRMObjectType.PERSON,
                label="Candidate person mapping",
                method=ep["person_create"]["method"],
                path=ep["person_create"]["path"],
                body={"name": person.display_name, "org_id": "{{organization.id}}"},
                dependencies=("organization",),
                status=SyncStatus.PREVIEWED if safe_to_map else SyncStatus.BLOCKED,
                blocked_reason=None if safe_to_map else "Person-to-canonical-CRM-organization mapping is not sufficiently resolved; do not silently merge the East Coast research entity into the ConstructConnect Houston/source account.",
                canonical_key=f"person:{person.id}",
            )

        lead_body = {
            "title": f"{project.canonical_name} | ConstructConnect {project.external_id}",
            "organization_id": "{{organization.id}}",
        }
        lead_req = IntegrationRequest(
            object_type=CRMObjectType.LEAD,
            label="Create qualified Lead",
            method=ep["lead_create"]["method"],
            path=ep["lead_create"]["path"],
            body=lead_body,
            dependencies=("organization",),
            status=SyncStatus.PREVIEWED if readiness.lead_ready else SyncStatus.BLOCKED,
            blocked_reason=None if readiness.lead_ready else ", ".join(readiness.lead_blockers),
            canonical_key=lead_key,
        )
        # The supplied Stafford $7.5B field is intentionally omitted from Lead/Deal value mapping.
        deal_body = {
            "title": project.canonical_name,
            "org_id": "{{organization.id}}",
        }
        if person_req and person_req.status is SyncStatus.PREVIEWED:
            deal_body["person_id"] = "{{person.id}}"
        deal_req = IntegrationRequest(
            object_type=CRMObjectType.DEAL,
            label="Promote commercially validated opportunity to Deal",
            method=ep["deal_create"]["method"],
            path=ep["deal_create"]["path"],
            body=deal_body,
            dependencies=("organization", "lead"),
            status=SyncStatus.PREVIEWED if readiness.deal_ready else SyncStatus.BLOCKED,
            blocked_reason=None if readiness.deal_ready else ", ".join(readiness.deal_blockers),
            canonical_key=deal_key,
        )
        requests = tuple(r for r in (org_req, person_req, lead_req, deal_req) if r is not None)
        for req in requests:
            self._persist_crm_preview(project, org, person if req.object_type is CRMObjectType.PERSON else None, req)
        self._audit(project, "PIPEDRIVE_DRY_RUN_PREVIEW", {
            "lead_ready": readiness.lead_ready,
            "deal_ready": readiness.deal_ready,
            "request_count": len(requests),
            "external_writes_executed": 0,
        })
        return PipedrivePreview(
            version=self.config.version,
            mode=self.pipedrive_mode.value,
            lead_ready=readiness.lead_ready,
            deal_ready=readiness.deal_ready,
            requests=requests,
            external_writes_executed=0,
            notes=(
                "Pipedrive is dry-run/preview only in Wave 10; no Off Grid credentials were used.",
                "Lead mapping deliberately omits Stafford's source-reported $7.5B as a monetary value because that phase-level value is not decision-trusted.",
                "Deal promotion is blocked until stronger commercial validation gates pass.",
            ),
        )

    def _persist_crm_preview(
        self,
        project: Project,
        organization: Organization,
        person: Person | None,
        req: IntegrationRequest,
    ) -> None:
        if req.object_type is None or not req.canonical_key:
            return
        promotion = {
            CRMObjectType.ORGANIZATION: CRMPromotionState.INTELLIGENCE,
            CRMObjectType.PERSON: CRMPromotionState.INTELLIGENCE,
            CRMObjectType.LEAD: CRMPromotionState.LEAD,
            CRMObjectType.DEAL: CRMPromotionState.DEAL,
        }[req.object_type]
        record = self.session.scalar(
            sa.select(CRMRecord).where(
                CRMRecord.crm_system == "pipedrive",
                CRMRecord.object_type == req.object_type,
                CRMRecord.canonical_key == req.canonical_key,
            )
        )
        if record is None:
            record = CRMRecord(
                crm_system="pipedrive",
                object_type=req.object_type,
                promotion_state=promotion,
                canonical_key=req.canonical_key,
                project_id=project.id,
                organization_id=organization.id,
                person_id=person.id if person else None,
                sync_status=req.status,
            )
            self.session.add(record)
            self.session.flush()
        else:
            record.sync_status = req.status
        request_payload = {"method": req.method, "path": req.path, "body": req.body}
        payload_text = json.dumps(request_payload, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
        idem = hashlib.sha256(
            f"pipedrive|{req.canonical_key}|{payload_hash}|{self.pipedrive_mode.value}".encode("utf-8")
        ).hexdigest()[:64]
        attempt = self.session.scalar(sa.select(CRMSyncAttempt).where(CRMSyncAttempt.idempotency_key == idem))
        if attempt is None:
            attempt = CRMSyncAttempt(
                crm_record_id=record.id,
                mode=self.pipedrive_mode,
                idempotency_key=idem,
                payload_hash=payload_hash,
                request_payload=request_payload,
                response_payload={"dry_run": True, "blocked_reason": req.blocked_reason},
                status=req.status,
                attempted_at=datetime.now(timezone.utc),
            )
            self.session.add(attempt)
        self.session.flush()

    def _sheets_preview(self, project: Project, readiness: CRMReadinessResult) -> SheetsPreview:
        cfg = self.reporting_cfg["sheets"]
        top_action = self.session.scalar(
            sa.select(NextAction)
            .where(NextAction.project_id == project.id, NextAction.status == ActionStatus.OPEN)
            .order_by(NextAction.priority.asc())
        )
        demos = self.session.scalar(
            sa.select(sa.func.count()).select_from(CommercialOutcome).where(
                CommercialOutcome.project_id == project.id,
                CommercialOutcome.outcome_type == CommercialOutcomeType.DEMO_BOOKED,
            )
        ) or 0
        all_outcomes = self.session.scalar(
            sa.select(sa.func.count()).select_from(CommercialOutcome).where(CommercialOutcome.project_id == project.id)
        ) or 0
        # Zero interview outcomes is not presented as a production KPI of zero; it is explicitly unavailable.
        demos_value: object = demos if all_outcomes else None
        row = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            project.external_id,
            project.canonical_name,
            float(readiness.commercial_fit),
            float(readiness.data_confidence),
            readiness.lead_ready,
            readiness.deal_ready,
            top_action.action_type if top_action else None,
            demos_value,
            "connected" if all_outcomes else "N/A — production outcome history not connected",
        )
        path = cfg["append_path_template"].format(
            spreadsheet_id="{{GOOGLE_SHEETS_SPREADSHEET_ID}}",
            range=cfg["range"],
        )
        result = SheetsPreview(
            version=self.config.reporting_version,
            method=cfg["append_method"],
            path=path,
            query={
                "valueInputOption": cfg["value_input_option"],
                "insertDataOption": cfg["insert_data_option"],
            },
            body={"majorDimension": "ROWS", "values": [list(row)]},
            columns=tuple(cfg["columns"]),
            row=row,
        )
        GoogleWorkspaceAdapter(self.google_mode).preview_report({"path": result.path, "body": result.body})
        self._audit(project, "GOOGLE_SHEETS_CONTRACT_PREVIEW", {"external_writes_executed": 0})
        return result

    def _forms_preview(self) -> FormsPreview:
        cfg = self.reporting_cfg["forms"]
        questions = tuple(dict(q) for q in cfg["questions"])
        requests = []
        for index, q in enumerate(questions):
            requests.append({
                "createItem": {
                    "item": {
                        "title": q["title"],
                        "questionItem": {"question": {"required": bool(q.get("required")), "textQuestion": {}}},
                    },
                    "location": {"index": index},
                }
            })
        return FormsPreview(
            version=self.config.reporting_version,
            create_method=cfg["create_method"],
            create_path=cfg["create_path"],
            create_body={"info": {"title": "Off Grid Commercial Outcome Feedback"}},
            batch_update_method=cfg["batch_update_method"],
            batch_update_path=cfg["batch_update_path_template"].format(form_id="{{GOOGLE_FORM_ID}}"),
            batch_update_body={"requests": requests},
            response_ingest_method=cfg["response_list_method"],
            response_ingest_path=cfg["response_list_path_template"].format(form_id="{{GOOGLE_FORM_ID}}"),
            response_submission_api_supported=GoogleWorkspaceAdapter.forms_response_submission_supported(),
            questions=questions,
        )

    def _trello_preview(self, project: Project) -> TrelloPreview:
        cfg = self.reporting_cfg["trello"]
        action = self.session.scalar(
            sa.select(NextAction)
            .where(NextAction.project_id == project.id, NextAction.status == ActionStatus.OPEN)
            .order_by(NextAction.priority.asc())
        )
        if action is None:
            action_name = "Review Stafford commercial intelligence exception"
            reason = "No open NextAction was available."
            action_id = "none"
        else:
            action_name = cfg["card_name_template"] if action.action_type == "VERIFY_SITE_EQUIPMENT_RESPONSIBILITY" else action.action_type
            reason = action.reason
            action_id = str(action.id)
        body = {
            "idList": cfg["list_id_placeholder"],
            "name": action_name,
            "desc": (
                f"Project: {project.canonical_name}\n"
                f"ConstructConnect ID: {project.external_id}\n"
                f"Action: {action.action_type if action else 'REVIEW'}\n"
                f"Reason: {reason}\n\n"
                "No raw source-contact phone numbers or email addresses are included in this preview."
            ),
        }
        idem = hashlib.sha256(f"trello|{project.external_id}|{action_id}".encode("utf-8")).hexdigest()[:64]
        result = TrelloPreview(
            version=self.config.reporting_version,
            method=cfg["create_method"],
            path=cfg["create_path"],
            body=body,
            idempotency_key=idem,
        )
        TrelloAdapter(self.trello_mode).preview_task(body)
        self._audit(project, "TRELLO_CARD_CONTRACT_PREVIEW", {"idempotency_key": idem, "external_writes_executed": 0})
        return result

    def _audit(self, project: Project, action: str, safe_metadata: dict) -> None:
        fingerprint = hashlib.sha256(json.dumps(safe_metadata, sort_keys=True).encode("utf-8")).hexdigest()
        existing = self.session.scalar(
            sa.select(AuditEvent).where(
                AuditEvent.actor_type == "SYSTEM",
                AuditEvent.actor_id == "wave10-integration-service",
                AuditEvent.action == action,
                AuditEvent.object_type == "PROJECT",
                AuditEvent.object_id == str(project.id),
                AuditEvent.after_hash == fingerprint,
            )
        )
        if existing is None:
            self.session.add(
                AuditEvent(
                    actor_type="SYSTEM",
                    actor_id="wave10-integration-service",
                    action=action,
                    object_type="PROJECT",
                    object_id=str(project.id),
                    reason="Wave 10 integration preview/contract generation; no external mutation executed.",
                    after_hash=fingerprint,
                    safe_metadata=safe_metadata,
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        self.session.flush()
