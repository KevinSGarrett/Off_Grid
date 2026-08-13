from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.commercial_workflow.config import CommercialWorkflowConfig, load_commercial_workflow_config
from app.commercial_workflow.outcomes import CommercialOutcomeService
from app.commercial_workflow.types import (
    CommercialMotionResult,
    DemandSignal,
    FirstCallKit,
    MotionFieldState,
    NextBestActionResult,
    OutcomeFeedbackModel,
    CommercialWorkflowResult,
)
from app.domain.states import (
    ActionStatus,
    ConfidenceState,
    ContactState,
    EvidenceClassification,
    MotionStatus,
    MotionType,
    VerificationState,
)
from app.models import (
    CommercialMotion,
    ConfigVersion,
    ContactAssessment,
    ContactCandidate,
    ExternalEvidence,
    NextAction,
    OpportunityAssessment,
    Organization,
    ProductFitAssessment,
    Project,
    ProjectOrganization,
)


class CommercialWorkflowService:
    """Create truthful linked contractor/channel motions and dependency-aware actions.

    The service consumes qualification, entity and contact state. It does not discover a new counterparty, send outreach,
    or write CRM state. Unknown rental authority/provider data remains unknown and causes actions
    to remain OPEN/BLOCKED rather than being filled with plausible-looking guesses.
    """

    def __init__(
        self,
        session: Session,
        config: CommercialWorkflowConfig | None = None,
    ):
        self.session = session
        self.config = config or load_commercial_workflow_config()
        self.workflow = self.config.workflow

    @property
    def version(self) -> str:
        return self.config.version

    def run(self, *, project_external_id: str) -> CommercialWorkflowResult:
        project = self.session.scalar(sa.select(Project).where(Project.external_id == project_external_id))
        if project is None:
            raise ValueError(f"Project not found: {project_external_id}")
        self._persist_config_version()

        assessment = self.session.scalar(
            sa.select(OpportunityAssessment)
            .where(OpportunityAssessment.project_id == project.id, OpportunityAssessment.is_current.is_(True))
            .order_by(OpportunityAssessment.computed_at.desc())
        )
        if assessment is None:
            raise ValueError("Commercial workflow requires a current persisted opportunity assessment")
        product_fits = self.session.scalars(
            sa.select(ProductFitAssessment).where(
                ProductFitAssessment.opportunity_assessment_id == assessment.id
            )
        ).all()
        demand_signal = self._demand_signal(product_fits)

        source_gc = self.session.scalar(
            sa.select(ProjectOrganization).where(
                ProjectOrganization.project_id == project.id,
                ProjectOrganization.role == "General Contractor",
            )
        )
        if source_gc is None:
            raise ValueError("Commercial workflow requires a source-backed Stafford general contractor relationship")
        gc_org = self.session.get(Organization, source_gc.organization_id)
        top_candidate, top_assessment = self._top_contact(project.id)

        contractor_motion = self._upsert_motion(
            project=project,
            motion_type=MotionType.CONTRACTOR,
            organization_id=gc_org.id,
            status=MotionStatus.VALIDATING,
            demand_strength=demand_signal.label,
            confidence_state=demand_signal.confidence_state,
            summary=(
                "Contractor/site-demand motion anchored to the ConstructConnect Stafford GC relationship. "
                "A strong Stafford-associated contact exists, but rental/equipment authority and actual "
                "temporary-lighting/mobile-power need remain unverified."
            ),
        )
        rental_motion = self._upsert_motion(
            project=project,
            motion_type=MotionType.RENTAL_HOUSE,
            organization_id=None,
            status=MotionStatus.UNRESOLVED,
            demand_strength="DEPENDENT_ON_VALIDATED_SITE_DEMAND",
            confidence_state=ConfidenceState.UNKNOWN,
            summary=(
                "Rental-house/channel motion is intentionally unresolved. No supplied or contact evidence "
                "establishes the Stafford rental provider, branch, or fleet buyer."
            ),
        )

        action_results = self._upsert_actions(
            project=project,
            contractor_motion=contractor_motion,
            rental_motion=rental_motion,
            top_candidate=top_candidate,
            top_assessment=top_assessment,
        )
        next_best = min(
            (row for row in action_results if row.status in {ActionStatus.OPEN, ActionStatus.IN_PROGRESS}),
            key=lambda row: (row.priority, row.action_type),
        )
        first_call = self._first_call_kit(top_candidate, top_assessment)
        outcome_model = self._outcome_feedback(project.id)
        contractor_result = self._contractor_result(
            contractor_motion, gc_org, top_candidate, top_assessment, demand_signal
        )
        rental_result = self._rental_result(rental_motion, demand_signal)

        unknowns = (
            "Who at Stafford actually controls or materially influences temporary lighting/mobile-power and rental decisions?",
            "Is there a verified current/upcoming temporary-lighting or mobile-power requirement?",
            "Which rental provider and branch currently serves the Stafford site?",
            "Who at that rental branch controls fleet acquisition/demo decisions?",
            "What incumbent equipment/supplier arrangement is already in place?",
        )
        self.session.commit()
        return CommercialWorkflowResult(
            workflow_version=self.version,
            project_id=project.id,
            project_external_id=project_external_id,
            demand_signal=demand_signal,
            contractor_motion=contractor_result,
            rental_house_motion=rental_result,
            next_actions=tuple(sorted(action_results, key=lambda row: (row.priority, row.action_type))),
            next_best_action=next_best,
            first_call_kit=first_call,
            decision_changing_unknowns=unknowns,
            outcome_feedback=outcome_model,
            external_writes_executed=0,
            outreach_messages_sent=0,
            notes=(
                "Contractor and rental-house motions are linked by the Stafford project but remain distinct.",
                "Doug Meadows is an investigation anchor only while rental_authority remains UNKNOWN.",
                "The commercial workflow records no fabricated calls, demos, rental providers, commercial outcomes, outreach, or CRM writes.",
            ),
        )

    def mark_action_complete(
        self,
        *,
        project_id: UUID,
        action_type: str,
        actor: str,
        reason: str,
    ) -> NextAction:
        """Record an externally performed/human-confirmed action; never performs the action itself."""
        row = self.session.scalar(
            sa.select(NextAction).where(
                NextAction.project_id == project_id,
                NextAction.action_type == action_type,
            )
        )
        if row is None:
            raise ValueError(f"Unknown action {action_type}")
        if row.status is ActionStatus.BLOCKED:
            dep = self.session.get(NextAction, row.dependency_action_id) if row.dependency_action_id else None
            if dep is None or dep.status is not ActionStatus.COMPLETE:
                raise ValueError("Blocked action cannot be completed before its dependency")
        if not actor.strip() or not reason.strip():
            raise ValueError("actor and reason are required")
        row.status = ActionStatus.COMPLETE
        row.completed_at = datetime.now(UTC)
        row.reason = f"{row.reason}\nCompletion evidence note: {reason.strip()} (recorded by {actor.strip()})"
        self.session.flush()
        self._refresh_dependency_statuses(project_id)
        self.session.commit()
        return row

    def current_first_call_kit(self, project_id: UUID) -> FirstCallKit:
        """Return the canonical, versioned kit without mutating workflow state."""
        top_candidate, top_assessment = self._top_contact(project_id)
        return self._first_call_kit(top_candidate, top_assessment)

    def _persist_config_version(self) -> ConfigVersion:
        existing = self.session.scalar(
            sa.select(ConfigVersion).where(
                ConfigVersion.config_kind == "commercial_workflow",
                ConfigVersion.version == self.version,
            )
        )
        if existing is not None:
            if existing.content_sha256 != self.config.loaded.sha256:
                raise ValueError("commercial workflow version reused with changed configuration")
            return existing
        for active in self.session.scalars(
            sa.select(ConfigVersion).where(
                ConfigVersion.config_kind == "commercial_workflow",
                ConfigVersion.is_active.is_(True),
            )
        ).all():
            active.is_active = False
        row = ConfigVersion(
            config_kind="commercial_workflow",
            version=self.version,
            content_sha256=self.config.loaded.sha256,
            source_path=str(self.config.loaded.path),
            content_text=self.config.loaded.text,
            activated_at=datetime.now(UTC),
            is_active=True,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _demand_signal(self, product_fits: list[ProductFitAssessment]) -> DemandSignal:
        cfg = self.workflow["demand_signal"]
        if not product_fits:
            return DemandSignal(
                label=str(cfg["labels"]["low"]),
                classification=EvidenceClassification.INFERRED,
                confidence_state=ConfidenceState.UNKNOWN,
                strongest_product_code=None,
                strongest_product_fit=None,
                rationale="No product-fit assessments are available; site demand remains unproven.",
                missing_evidence=("verified lighting need", "verified mobile-power need"),
            )
        top = max(product_fits, key=lambda row: (Decimal(row.fit_score), row.product_code))
        score = Decimal(top.fit_score)
        if score >= Decimal(str(cfg["high_threshold"])):
            label = str(cfg["labels"]["high"])
        elif score >= Decimal(str(cfg["medium_threshold"])):
            label = str(cfg["labels"]["medium"])
        else:
            label = str(cfg["labels"]["low"])
        missing: list[str] = []
        for fit in product_fits:
            if fit.missing_evidence:
                missing.extend(part.strip() for part in re.split(r"[;\n]+", fit.missing_evidence) if part.strip())
        return DemandSignal(
            label=label,
            classification=EvidenceClassification.INFERRED,
            confidence_state=ConfidenceState(str(cfg["confidence_state"])),
            strongest_product_code=top.product_code,
            strongest_product_fit=score,
            rationale=(
                f"Strongest current product fit is {top.product_code} at {score:.3f}/100. "
                "That supports prioritizing validation, not claiming proven site demand."
            ),
            missing_evidence=tuple(dict.fromkeys(missing)),
        )

    def _top_contact(self, project_id: UUID) -> tuple[ContactCandidate | None, ContactAssessment | None]:
        candidate = self.session.scalar(
            sa.select(ContactCandidate)
            .where(ContactCandidate.project_id == project_id, ContactCandidate.is_current.is_(True))
            .order_by(ContactCandidate.rank.asc().nulls_last(), ContactCandidate.candidate_score.desc())
        )
        if candidate is None:
            return None, None
        assessment = self.session.scalar(
            sa.select(ContactAssessment)
            .where(ContactAssessment.candidate_id == candidate.id, ContactAssessment.is_current.is_(True))
            .order_by(ContactAssessment.assessed_at.desc())
        )
        return candidate, assessment

    def _upsert_motion(
        self,
        *,
        project: Project,
        motion_type: MotionType,
        organization_id: UUID | None,
        status: MotionStatus,
        demand_strength: str,
        confidence_state: ConfidenceState,
        summary: str,
    ) -> CommercialMotion:
        row = self.session.scalar(
            sa.select(CommercialMotion).where(
                CommercialMotion.project_id == project.id,
                CommercialMotion.motion_type == motion_type,
            )
        )
        if row is None:
            row = CommercialMotion(project_id=project.id, motion_type=motion_type)
            self.session.add(row)
        row.organization_id = organization_id
        row.status = status
        row.demand_strength = demand_strength
        row.confidence_state = confidence_state
        row.owner = str(self.workflow.get("owner") or "commercial_research")
        row.summary = summary
        self.session.flush()
        return row

    def _upsert_actions(
        self,
        *,
        project: Project,
        contractor_motion: CommercialMotion,
        rental_motion: CommercialMotion,
        top_candidate: ContactCandidate | None,
        top_assessment: ContactAssessment | None,
    ) -> tuple[NextBestActionResult, ...]:
        action_cfg = {str(row["key"]): row for row in self.workflow["actions"]}
        rows: dict[str, NextAction] = {}
        external_evidence_id = self._project_contact_evidence(top_candidate)

        for key, cfg in action_cfg.items():
            existing = self.session.scalar(
                sa.select(NextAction).where(
                    NextAction.project_id == project.id,
                    NextAction.action_type == key,
                )
            )
            if existing is None:
                existing = NextAction(project_id=project.id, action_type=key, reason=str(cfg["reason"]))
                self.session.add(existing)
            existing.commercial_motion_id = (
                contractor_motion.id if cfg["motion"] == "CONTRACTOR" else rental_motion.id
            )
            existing.priority = int(cfg["priority"])
            existing.owner = str(cfg["owner"])
            existing.reason = str(cfg["reason"])
            if key == "VERIFY_SITE_EQUIPMENT_RESPONSIBILITY":
                existing.external_evidence_id = external_evidence_id
            rows[key] = existing
        self.session.flush()

        for key, cfg in action_cfg.items():
            dependency = cfg.get("dependency")
            row = rows[key]
            row.dependency_action_id = rows[str(dependency)].id if dependency else None
            if row.status is ActionStatus.COMPLETE:
                continue
            if key == "VERIFY_SITE_EQUIPMENT_RESPONSIBILITY" and self._authority_verified(top_assessment):
                row.status = ActionStatus.COMPLETE
                row.completed_at = row.completed_at or datetime.now(UTC)
                continue
            if dependency:
                row.status = (
                    ActionStatus.OPEN
                    if rows[str(dependency)].status is ActionStatus.COMPLETE
                    else ActionStatus.BLOCKED
                )
            else:
                row.status = ActionStatus.OPEN
        self.session.flush()

        result: list[NextBestActionResult] = []
        for key, cfg in action_cfg.items():
            row = rows[key]
            dep_key = str(cfg["dependency"]) if cfg.get("dependency") else None
            result.append(
                NextBestActionResult(
                    action_id=row.id,
                    action_type=key,
                    motion_type=MotionType(str(cfg["motion"])),
                    status=row.status,
                    priority=row.priority,
                    owner=row.owner or "",
                    execution_mode=str(cfg["execution_mode"]),
                    reason=row.reason,
                    dependency_action_type=dep_key,
                    dependency_action_id=row.dependency_action_id,
                    source_evidence_id=row.source_evidence_id,
                    external_evidence_id=row.external_evidence_id,
                    immediately_executable=(
                        row.status in {ActionStatus.OPEN, ActionStatus.IN_PROGRESS}
                        and not str(cfg["execution_mode"]).startswith("AUTOMATED_WRITE")
                    ),
                )
            )
        return tuple(result)

    def _refresh_dependency_statuses(self, project_id: UUID) -> None:
        rows = self.session.scalars(sa.select(NextAction).where(NextAction.project_id == project_id)).all()
        by_id = {row.id: row for row in rows}
        for row in rows:
            if row.status is ActionStatus.COMPLETE:
                continue
            if row.dependency_action_id is None:
                row.status = ActionStatus.OPEN
                continue
            dep = by_id.get(row.dependency_action_id)
            row.status = ActionStatus.OPEN if dep and dep.status is ActionStatus.COMPLETE else ActionStatus.BLOCKED
        self.session.flush()

    @staticmethod
    def _authority_verified(assessment: ContactAssessment | None) -> bool:
        return bool(assessment and assessment.rental_authority_state is VerificationState.VERIFIED)

    def _project_contact_evidence(self, candidate: ContactCandidate | None) -> UUID | None:
        if candidate is None:
            return None
        row = self.session.scalar(
            sa.select(ExternalEvidence)
            .where(
                ExternalEvidence.project_id == candidate.project_id,
                ExternalEvidence.person_id == candidate.person_id,
                ExternalEvidence.verification_state == VerificationState.VERIFIED,
            )
            .order_by(ExternalEvidence.retrieved_at.desc())
        )
        return row.id if row else None

    def _first_call_kit(
        self,
        candidate: ContactCandidate | None,
        assessment: ContactAssessment | None,
    ) -> FirstCallKit:
        cfg = self.workflow["first_call_kit"]
        if candidate is None:
            target_name = "UNRESOLVED"
            target_status = "NO_EVIDENCE_BACKED_CANDIDATE"
        else:
            from app.models import Person

            person = self.session.get(Person, candidate.person_id)
            target_name = person.display_name if person else "UNRESOLVED"
            authority = assessment.rental_authority_state.value if assessment else "UNKNOWN"
            target_status = f"{candidate.state.value}; rental_authority={authority}"
        return FirstCallKit(
            version=str(cfg["version"]),
            target_candidate_id=candidate.id if candidate else None,
            target_person_name=target_name,
            target_status=target_status,
            objective=str(cfg["objective"]),
            questions=tuple(str(item) for item in cfg["questions"]),
            after_call_capture=tuple(str(item) for item in cfg["after_call_capture"]),
            safeguards=(
                "Use this as a validation script, not proof that the target is the decision maker.",
                "Do not represent the interview project as acting on behalf of Off Grid without authorization.",
                "Record the verification source and preserve UNKNOWN when a question is not answered.",
            ),
        )

    def _outcome_feedback(self, project_id: UUID) -> OutcomeFeedbackModel:
        cfg = self.workflow["outcomes"]
        return OutcomeFeedbackModel(
            version=str(cfg["model_version"]),
            contact_outcomes=tuple(str(item) for item in cfg["categories"]["contact"]),
            project_outcomes=tuple(str(item) for item in cfg["categories"]["project"]),
            commercial_outcomes=tuple(str(item) for item in cfg["categories"]["commercial"]),
            loss_reasons=tuple(str(item) for item in cfg["loss_reasons"]),
            stored_outcome_count=CommercialOutcomeService(self.session).count(project_id),
            predictive_ml_trained=False,
            notes=(
                "The commercial workflow creates structured feedback capture but records no fabricated activity.",
                "Future calibration can analyze stored labels after real commercial history exists.",
            ),
        )

    def _contractor_result(
        self,
        motion: CommercialMotion,
        organization: Organization,
        candidate: ContactCandidate | None,
        assessment: ContactAssessment | None,
        demand_signal: DemandSignal,
    ) -> CommercialMotionResult:
        candidate_name = "UNRESOLVED"
        candidate_state = VerificationState.UNKNOWN
        authority_state = VerificationState.UNKNOWN
        if candidate is not None:
            from app.models import Person

            person = self.session.get(Person, candidate.person_id)
            candidate_name = person.display_name if person else "UNRESOLVED"
            candidate_state = (
                VerificationState.VERIFIED
                if candidate.state in {ContactState.PROJECT_ASSOCIATION_VERIFIED, ContactState.ROLE_RELEVANT, ContactState.AUTHORITY_VERIFIED}
                else VerificationState.SUPPORTED
            )
            if assessment is not None:
                authority_state = assessment.rental_authority_state
        fields = (
            MotionFieldState("project", "Stafford Technology Campus Phases 3 & 4", VerificationState.VERIFIED, "Canonical real project from ConstructConnect."),
            MotionFieldState("general_contractor", organization.canonical_name, VerificationState.VERIFIED, "Source-backed Stafford GC relationship; operating-division ambiguity remains separate."),
            MotionFieldState("site_contact_investigation_anchor", candidate_name, candidate_state, "Highest-ranked evidence-backed Stafford contact candidate; not equivalent to authority."),
            MotionFieldState("temporary_lighting_power_responsibility", "UNKNOWN", authority_state, "No evidence currently proves who controls this category."),
            MotionFieldState("equipment_arrangement", "UNKNOWN", VerificationState.UNKNOWN, "Current equipment/incumbent arrangement is not in supplied or bounded public evidence."),
            MotionFieldState("site_demand", demand_signal.label, VerificationState.SUPPORTED, "Derived from product-fit inference and therefore requires direct validation."),
            MotionFieldState("site_demo_demand", "UNKNOWN", VerificationState.UNKNOWN, "No demo interest/activity has been fabricated."),
        )
        return CommercialMotionResult(
            motion_id=motion.id,
            motion_type=motion.motion_type,
            status=motion.status,
            organization_id=organization.id,
            organization_name=organization.canonical_name,
            demand_strength=motion.demand_strength,
            confidence_state=motion.confidence_state,
            summary=motion.summary or "",
            fields=fields,
        )

    def _rental_result(
        self,
        motion: CommercialMotion,
        demand_signal: DemandSignal,
    ) -> CommercialMotionResult:
        fields = (
            MotionFieldState("rental_provider", "UNRESOLVED", VerificationState.UNKNOWN, "No Stafford rental provider is established by the supplied PDFs or bounded public research."),
            MotionFieldState("rental_branch", "UNRESOLVED", VerificationState.UNKNOWN, "Branch resolution depends on first identifying the actual provider."),
            MotionFieldState("fleet_buyer", "UNRESOLVED", VerificationState.UNKNOWN, "Do not search/claim a fleet buyer until provider/branch identity is established."),
            MotionFieldState("contractor_demand_signal", demand_signal.label, VerificationState.SUPPORTED, "Commercial inference from Stafford product-fit evidence; not yet direct demand proof."),
            MotionFieldState("fleet_opportunity", "UNRESOLVED", VerificationState.UNKNOWN, "Fleet opportunity depends on validated contractor demand and rental-channel identity."),
            MotionFieldState("demo_purchase_path", "UNRESOLVED", VerificationState.UNKNOWN, "No rental-channel demo/purchase activity exists in the interview evidence."),
        )
        return CommercialMotionResult(
            motion_id=motion.id,
            motion_type=motion.motion_type,
            status=motion.status,
            organization_id=None,
            organization_name=None,
            demand_strength=motion.demand_strength,
            confidence_state=motion.confidence_state,
            summary=motion.summary or "",
            fields=fields,
        )
