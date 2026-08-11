from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.commercial_workflow.service import Wave09CommercialWorkflowService
from app.contact_resolution.service import Wave08ContactResolutionService
from app.crm.config import load_crm_integration_config
from app.crm.service import Wave10IntegrationService
from app.domain.errors import ExternalWriteBlocked
from app.domain.states import CRMPromotionState, CRMObjectType, IntegrationMode, SyncStatus
from app.ingestion.service import ConstructConnectIngestionService
from app.integrations.pipedrive import PipedriveAdapter
from app.models import AuditEvent, Base, CRMRecord, CRMSyncAttempt, Project
from app.persistence.database import build_engine
from app.resolution.service import Wave07ResolutionService
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[2]
STAFFORD = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"
EE_REED = ROOT / "context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf"


def _session() -> Session:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _build(session: Session):
    ingest = ConstructConnectIngestionService(session)
    ingest.ingest(STAFFORD)
    ingest.ingest(EE_REED)
    stafford = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
    assert stafford is not None
    QualificationService(session).evaluate(stafford.id, persist=True)
    Wave07ResolutionService(session).run()
    Wave08ContactResolutionService(session).run()
    Wave09CommercialWorkflowService(session).run()
    return stafford, Wave10IntegrationService(session).run()


@pytest.fixture(scope="module")
def built():
    session = _session()
    project, result = _build(session)
    yield session, project, result
    session.close()


def test_wave10_stafford_is_lead_ready_but_not_deal_ready(built) -> None:
    _session_obj, _project, result = built
    assert result.readiness.lead_ready is True
    assert result.readiness.deal_ready is False
    assert result.readiness.permitted_promotion is CRMPromotionState.LEAD
    assert result.readiness.lead_blockers == ()
    assert set(result.readiness.deal_blockers) >= {
        "rental_authority_verified",
        "site_need_verified",
        "rental_provider_resolved",
        "rental_branch_or_fleet_buyer_resolved",
    }


def test_pipedrive_contract_uses_current_official_endpoint_versions(built) -> None:
    _session_obj, _project, result = built
    by_type = {row.object_type: row for row in result.pipedrive.requests}
    assert by_type[CRMObjectType.ORGANIZATION].path == "/api/v2/organizations"
    assert by_type[CRMObjectType.PERSON].path == "/api/v2/persons"
    assert by_type[CRMObjectType.LEAD].path == "/api/v1/leads"
    assert by_type[CRMObjectType.DEAL].path == "/api/v2/deals"
    assert all(row.method == "POST" for row in by_type.values())


def test_lead_payload_links_to_organization_and_does_not_send_untrusted_stafford_value(built) -> None:
    _session_obj, _project, result = built
    lead = next(row for row in result.pipedrive.requests if row.object_type is CRMObjectType.LEAD)
    assert lead.status is SyncStatus.PREVIEWED
    assert lead.body["organization_id"] == "{{organization.id}}"
    assert "1007341663" in lead.body["title"]
    assert "value" not in lead.body
    assert "7500000000" not in str(lead.body)


def test_person_mapping_is_blocked_when_research_entity_and_source_account_are_not_resolved(built) -> None:
    _session_obj, _project, result = built
    person = next(row for row in result.pipedrive.requests if row.object_type is CRMObjectType.PERSON)
    assert person.body["name"] == "Doug Meadows"
    assert person.status is SyncStatus.BLOCKED
    assert "do not silently merge" in (person.blocked_reason or "")


def test_deal_payload_is_blocked_by_deterministic_readiness_gate(built) -> None:
    _session_obj, _project, result = built
    deal = next(row for row in result.pipedrive.requests if row.object_type is CRMObjectType.DEAL)
    assert deal.status is SyncStatus.BLOCKED
    assert "rental_authority_verified" in (deal.blocked_reason or "")
    assert "value" not in deal.body


def test_crm_preview_is_idempotent_for_records_and_sync_attempts(built) -> None:
    session, project, first = built
    second = Wave10IntegrationService(session).run()
    assert first.crm_record_count == second.crm_record_count == 4
    assert first.crm_sync_attempt_count == second.crm_sync_attempt_count == 4
    count_records = session.scalar(
        sa.select(sa.func.count()).select_from(CRMRecord).where(CRMRecord.project_id == project.id)
    )
    assert count_records == 4
    assert session.scalar(sa.select(sa.func.count()).select_from(CRMSyncAttempt)) == 4


def test_demo_mode_blocks_live_pipedrive_write_even_if_other_conditions_pass() -> None:
    adapter = PipedriveAdapter(
        mode=IntegrationMode.LIVE,
        demo_mode=True,
        credentials_present=True,
        transport=None,
    )
    with pytest.raises(ExternalWriteBlocked, match="DEMO_MODE"):
        adapter.execute(
            "POST",
            "/api/v2/organizations",
            {"name": "Example"},
            readiness_passed=True,
        )


def test_sheets_contract_is_append_ready_and_does_not_fabricate_demo_metric(built) -> None:
    _session_obj, _project, result = built
    assert result.sheets.method == "POST"
    assert result.sheets.path.endswith(":append")
    assert result.sheets.query["valueInputOption"] == "RAW"
    assert result.sheets.query["insertDataOption"] == "INSERT_ROWS"
    demo_index = result.sheets.columns.index("system_sourced_demos_rolling_30d")
    status_index = result.sheets.columns.index("outcome_data_status")
    assert result.sheets.row[demo_index] is None
    assert "not connected" in str(result.sheets.row[status_index]).lower()


def test_forms_contract_creates_structure_but_reads_submitted_responses_instead_of_fake_api_submission(built) -> None:
    _session_obj, _project, result = built
    assert result.forms.create_method == "POST"
    assert result.forms.create_path == "/v1/forms"
    assert result.forms.batch_update_path.endswith(":batchUpdate")
    assert result.forms.response_ingest_method == "GET"
    assert result.forms.response_ingest_path.endswith("/responses")
    assert result.forms.response_submission_api_supported is False
    assert len(result.forms.questions) >= 7


def test_trello_contract_is_card_preview_with_minimal_pii(built) -> None:
    _session_obj, _project, result = built
    assert result.trello.method == "POST"
    assert result.trello.path == "/1/cards"
    assert result.trello.body["idList"] == "{{TRELLO_REVIEW_LIST_ID}}"
    assert "Verify Stafford" in result.trello.body["name"]
    desc = result.trello.body["desc"]
    assert "1007341663" in desc
    assert "@eereed.com" not in desc
    assert "(281)" not in desc


def test_external_integration_contracts_execute_zero_writes_in_wave10(built) -> None:
    _session_obj, _project, result = built
    assert result.external_writes_executed == 0
    assert result.pipedrive.external_writes_executed == 0
    assert result.sheets.external_writes_executed == 0
    assert result.forms.external_writes_executed == 0
    assert result.trello.external_writes_executed == 0


def test_dry_run_and_contract_previews_are_audited(built) -> None:
    session, project, result = built
    actions = set(
        session.scalars(
            sa.select(AuditEvent.action).where(AuditEvent.object_id == str(project.id))
        ).all()
    )
    assert {
        "PIPEDRIVE_DRY_RUN_PREVIEW",
        "GOOGLE_SHEETS_CONTRACT_PREVIEW",
        "TRELLO_CARD_CONTRACT_PREVIEW",
    }.issubset(actions)
    assert result.audit_event_count >= 3


def test_integrations_configuration_has_safe_defaults_and_explicit_versions() -> None:
    cfg = load_crm_integration_config(ROOT / "config/integrations.yaml")
    assert cfg.version == "pipedrive-1.0"
    assert cfg.reporting_version == "reporting-integrations-1.0"
    assert cfg.crm["default_mode"] == "dry_run"
    assert cfg.crm["demo_mode_external_writes"] is False
    assert cfg.reporting["forms"]["response_submission_api_supported"] is False
