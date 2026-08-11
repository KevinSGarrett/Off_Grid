from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.commercial_workflow.outcomes import CommercialOutcomeService
from app.commercial_workflow.service import Wave09CommercialWorkflowService
from app.contact_resolution.service import Wave08ContactResolutionService
from app.contact_resolution.verification import ContactVerificationService
from app.domain.states import (
    ActionStatus,
    CommercialOutcomeType,
    LossReason,
    MotionStatus,
    MotionType,
    VerificationState,
)
from app.ingestion.service import ConstructConnectIngestionService
from app.models import Base, CommercialMotion, CommercialOutcome, NextAction, Organization, Project
from app.persistence.database import build_engine
from app.resolution.service import Wave07ResolutionService
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"
EXPECTED = json.loads((ROOT / "tests/golden/stafford_wave09_expected.json").read_text())


_BASELINE_DIR = Path(tempfile.mkdtemp(prefix="offgrid-wave09-tests-"))
_BASELINE_DB = _BASELINE_DIR / "ingested.db"


def _ensure_ingested_baseline() -> None:
    """Parse the two golden PDFs once, then clone that database per Wave 09 test.

    Re-parsing the nine-page company fixture eleven times in one pytest process is
    unnecessary for Wave 09's commercial-workflow assertions and can make the
    complete reliability suite resource-bound. Ingestion correctness remains
    covered by the Wave 05 and Wave 14 golden/integration lanes.
    """

    if _BASELINE_DB.exists():
        return
    engine = build_engine(f"sqlite+pysqlite:///{_BASELINE_DB}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            ingest = ConstructConnectIngestionService(session)
            ingest.ingest(STAFFORD)
            ingest.ingest(EE_REED)
            session.commit()
    finally:
        engine.dispose()


@contextmanager
def _session():
    """Create an isolated session from the immutable real-source ingest baseline."""

    _ensure_ingested_baseline()
    test_db = _BASELINE_DIR / f"case-{uuid.uuid4().hex}.db"
    shutil.copy2(_BASELINE_DB, test_db)
    engine = build_engine(f"sqlite+pysqlite:///{test_db}")
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()
        test_db.unlink(missing_ok=True)


def _build_through_wave09(session: Session):
    stafford = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    score = QualificationService(session).evaluate(stafford.id, persist=True)
    Wave07ResolutionService(session).run()
    contacts = Wave08ContactResolutionService(session).run()
    workflow = Wave09CommercialWorkflowService(session).run()
    return stafford, score, contacts, workflow


def test_wave09_creates_two_linked_but_distinct_commercial_motions() -> None:
    with _session() as session:
        stafford, _, _, result = _build_through_wave09(session)
        assert result.workflow_version == EXPECTED["workflow_version"]
        assert result.contractor_motion.motion_type is MotionType.CONTRACTOR
        assert result.rental_house_motion.motion_type is MotionType.RENTAL_HOUSE
        assert result.contractor_motion.motion_id != result.rental_house_motion.motion_id
        assert result.contractor_motion.status.value == EXPECTED["contractor_motion_status"]
        assert result.rental_house_motion.status.value == EXPECTED["rental_motion_status"]
        assert session.scalar(
            sa.select(sa.func.count()).select_from(CommercialMotion).where(
                CommercialMotion.project_id == stafford.id
            )
        ) == 2


def test_contractor_motion_uses_source_gc_and_keeps_contact_authority_unknown() -> None:
    with _session() as session:
        _, _, contacts, result = _build_through_wave09(session)
        assert result.contractor_motion.organization_name == EXPECTED["contractor_organization"]
        assert result.first_call_kit.target_person_name == EXPECTED["top_contact"]
        assert contacts.candidates[0].rental_authority_state.value == EXPECTED["top_contact_authority"]
        fields = {row.key: row for row in result.contractor_motion.fields}
        assert fields["temporary_lighting_power_responsibility"].value == "UNKNOWN"
        assert fields["temporary_lighting_power_responsibility"].verification_state is VerificationState.UNKNOWN
        assert "not equivalent to authority" in fields["site_contact_investigation_anchor"].rationale


def test_rental_house_motion_explicitly_preserves_unresolved_provider_branch_and_buyer() -> None:
    with _session() as session:
        _, _, _, result = _build_through_wave09(session)
        assert result.rental_house_motion.organization_id is None
        assert result.rental_house_motion.status is MotionStatus.UNRESOLVED
        fields = {row.key: row for row in result.rental_house_motion.fields}
        assert fields["rental_provider"].value == EXPECTED["rental_provider"]
        assert fields["rental_provider"].verification_state is VerificationState.UNKNOWN
        assert fields["rental_branch"].value == "UNRESOLVED"
        assert fields["fleet_buyer"].value == "UNRESOLVED"
        assert fields["fleet_opportunity"].value == "UNRESOLVED"


def test_demand_signal_is_derived_from_current_product_fit_not_claimed_as_verified_need() -> None:
    with _session() as session:
        _, score, _, result = _build_through_wave09(session)
        strongest = max(score.product_fits, key=lambda row: (row.fit_score, row.product_code))
        assert result.demand_signal.strongest_product_code == strongest.product_code
        assert result.demand_signal.strongest_product_fit == strongest.fit_score
        assert result.demand_signal.classification.value == "INFERRED"
        assert "validation" in result.demand_signal.rationale.lower()
        assert result.contractor_motion.status is MotionStatus.VALIDATING


def test_next_best_action_is_dependency_aware_and_human_bounded() -> None:
    with _session() as session:
        _, _, _, result = _build_through_wave09(session)
        assert result.next_best_action.action_type == EXPECTED["next_best_action"]
        assert result.next_best_action.status.value == EXPECTED["next_best_action_status"]
        assert set(row.action_type for row in result.next_actions) == set(EXPECTED["required_action_types"])
        by_type = {row.action_type: row for row in result.next_actions}
        assert by_type["VERIFY_SITE_EQUIPMENT_RESPONSIBILITY"].status is ActionStatus.OPEN
        assert by_type["VALIDATE_TEMP_LIGHTING_POWER_NEED"].status is ActionStatus.BLOCKED
        assert by_type["IDENTIFY_INCUMBENT_RENTAL_PROVIDER"].status is ActionStatus.BLOCKED
        assert by_type["RESOLVE_RENTAL_BRANCH_FLEET_BUYER"].status is ActionStatus.BLOCKED
        assert by_type["VALIDATE_FLEET_OPPORTUNITY"].status is ActionStatus.BLOCKED
        assert all(
            row.execution_mode.startswith("HUMAN")
            for row in result.next_actions
        )
        assert result.external_writes_executed == 0
        assert result.outreach_messages_sent == 0


def test_first_call_kit_operationalizes_decision_changing_unknowns() -> None:
    with _session() as session:
        _, _, _, result = _build_through_wave09(session)
        kit = result.first_call_kit
        assert kit.version == EXPECTED["first_call_kit_version"]
        assert len(kit.questions) >= 6
        text = " ".join(kit.questions).lower()
        for required in ("temporary lighting", "mobile power", "rental", "diesel light towers", "upcoming", "demo"):
            assert required in text
        capture = set(kit.after_call_capture)
        assert {"rental_provider_identified", "rental_authority_status", "demo_interest"} <= capture
        assert "rental_authority=UNKNOWN" in kit.target_status


def test_wave09_is_idempotent_for_motions_actions_and_base_outcomes() -> None:
    with _session() as session:
        stafford, _, _, first = _build_through_wave09(session)
        motion_count = session.scalar(sa.select(sa.func.count()).select_from(CommercialMotion))
        action_count = session.scalar(sa.select(sa.func.count()).select_from(NextAction))
        outcome_count = session.scalar(sa.select(sa.func.count()).select_from(CommercialOutcome))
        second = Wave09CommercialWorkflowService(session).run()
        assert session.scalar(sa.select(sa.func.count()).select_from(CommercialMotion)) == motion_count == 2
        assert session.scalar(sa.select(sa.func.count()).select_from(NextAction)) == action_count == len(first.next_actions)
        assert session.scalar(sa.select(sa.func.count()).select_from(CommercialOutcome)) == outcome_count == 0
        assert second.project_id == stafford.id
        assert second.outcome_feedback.stored_outcome_count == EXPECTED["initial_stored_outcomes"]


def test_authorized_authority_verification_advances_dependency_without_sending_anything() -> None:
    with _session() as session:
        _, _, contacts, _ = _build_through_wave09(session)
        doug = contacts.candidates[0]
        ContactVerificationService(session).record(
            candidate_id=doug.candidate_id,
            dimension="rental_authority",
            verification_type="PHONE_CONFIRMATION",
            outcome=VerificationState.VERIFIED,
            verified_by="authorized_human_reviewer",
            note="Test-only recorded verification; the application performs no phone call.",
        )
        result = Wave09CommercialWorkflowService(session).run()
        by_type = {row.action_type: row for row in result.next_actions}
        assert by_type["VERIFY_SITE_EQUIPMENT_RESPONSIBILITY"].status is ActionStatus.COMPLETE
        assert by_type["VALIDATE_TEMP_LIGHTING_POWER_NEED"].status is ActionStatus.OPEN
        assert result.next_best_action.action_type == "VALIDATE_TEMP_LIGHTING_POWER_NEED"
        assert result.external_writes_executed == 0
        assert result.outreach_messages_sent == 0


def test_outcome_feedback_records_real_observations_only_and_supports_future_analysis() -> None:
    with _session() as session:
        stafford, _, contacts, result = _build_through_wave09(session)
        service = CommercialOutcomeService(session)
        contact = service.record(
            project_id=stafford.id,
            contact_candidate_id=contacts.candidates[0].candidate_id,
            outcome_type=CommercialOutcomeType.RIGHT_PERSON,
            source="authorized_test_observation",
            observed_at=datetime.now(timezone.utc),
            notes="Test fixture only.",
        )
        commercial = service.record(
            project_id=stafford.id,
            commercial_motion_id=result.contractor_motion.motion_id,
            outcome_type=CommercialOutcomeType.LOST,
            loss_reason=LossReason.INCUMBENT_SUPPLIER,
            source="authorized_test_observation",
            observed_at=datetime.now(timezone.utc),
            notes="Test fixture only.",
        )
        session.commit()
        assert contact.outcome_type is CommercialOutcomeType.RIGHT_PERSON
        assert commercial.loss_reason is LossReason.INCUMBENT_SUPPLIER
        rows = service.feature_outcome_export(stafford.id)
        assert {row["outcome_type"] for row in rows} == {"RIGHT_PERSON", "LOST"}
        assert service.count(stafford.id) == 2


def test_outcome_service_rejects_invalid_or_unattributed_feedback() -> None:
    import pytest

    with _session() as session:
        stafford, _, _, result = _build_through_wave09(session)
        service = CommercialOutcomeService(session)
        with pytest.raises(ValueError, match="source is required"):
            service.record(
                project_id=stafford.id,
                commercial_motion_id=result.contractor_motion.motion_id,
                outcome_type=CommercialOutcomeType.RESPONDED,
                source="",
            )
        with pytest.raises(ValueError, match="LOST outcomes require"):
            service.record(
                project_id=stafford.id,
                commercial_motion_id=result.contractor_motion.motion_id,
                outcome_type=CommercialOutcomeType.LOST,
                source="authorized_test_observation",
            )
        with pytest.raises(ValueError, match="permitted only for LOST"):
            service.record(
                project_id=stafford.id,
                commercial_motion_id=result.contractor_motion.motion_id,
                outcome_type=CommercialOutcomeType.INTERESTED,
                loss_reason=LossReason.PRICE,
                source="authorized_test_observation",
            )


def test_wave09_does_not_train_or_claim_predictive_ml() -> None:
    with _session() as session:
        _, _, _, result = _build_through_wave09(session)
        assert result.outcome_feedback.version == EXPECTED["outcome_model_version"]
        assert result.outcome_feedback.predictive_ml_trained is False
        assert result.outcome_feedback.stored_outcome_count == 0
        config_text = (ROOT / "config/commercial_workflow.yaml").read_text().lower()
        assert "do not train or claim predictive ml" in config_text
