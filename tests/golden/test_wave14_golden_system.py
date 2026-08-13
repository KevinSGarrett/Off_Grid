from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from app.models import (
    ContactCandidate,
    OrganizationDomain,
    PipelineEvent,
    PipelineRun,
    Project,
    QualityFlag,
    SourceObservation,
)


def test_real_stafford_golden_truth_and_quality_survive_wave14(wave14_full_state) -> None:
    factory = wave14_full_state["factory"]
    project_id = wave14_full_state["ids"]["project"]
    with factory() as session:
        project = session.get(Project, project_id)
        assert project is not None
        assert project.external_id == "1007341663"
        assert project.reported_value == Decimal("7500000000.00")
        assert "General Contractor Award" in (project.stage or "")
        codes = set(
            session.scalars(sa.select(QualityFlag.rule_code).where(QualityFlag.project_id == project.id)).all()
        )
        assert {"FUTURE_ACTUAL_DATE", "PROJECT_VALUE_UNCERTAINTY", "MISSING_PROJECT_GC_CONTACT"} <= codes
        assert wave14_full_state["assessment"].disposition == "VERIFY"
        assert wave14_full_state["assessment"].overall_band == "Promising candidate"
        assert wave14_full_state["assessment"].commercial_fit_score == Decimal("57.00")


def test_real_ee_reed_reconciliation_duplicates_domains_and_generic_inboxes(wave14_full_state) -> None:
    factory = wave14_full_state["factory"]
    organization_id = wave14_full_state["ids"]["organization"]
    with factory() as session:
        counts = {
            row.field_name: row.normalized_integer
            for row in session.scalars(
                sa.select(SourceObservation).where(
                    SourceObservation.organization_id == organization_id,
                    SourceObservation.field_name.in_([
                        "organization.planning_project_count",
                        "organization.post_bid_project_count",
                        "organization.bidding_role_project_count",
                    ]),
                )
            ).all()
        }
        assert counts == {
            "organization.planning_project_count": 6,
            "organization.post_bid_project_count": 87,
            "organization.bidding_role_project_count": 74,
        }
        codes = set(
            session.scalars(sa.select(QualityFlag.rule_code).where(QualityFlag.organization_id == organization_id)).all()
        )
        assert {"GENERIC_CONTACT_EMAIL", "ORGANIZATION_DOMAIN_CONFLICT", "POSSIBLE_DUPLICATE_CONTACT"} <= codes
        domains = set(
            session.scalars(
                sa.select(OrganizationDomain.normalized_domain).where(OrganizationDomain.organization_id == organization_id)
            ).all()
        )
        assert {"eereed.com", "eereedeast.com", "zapalacreed.com"} <= domains


def test_real_contact_candidate_remains_investigation_anchor_not_verified_rental_authority(wave14_full_state) -> None:
    factory = wave14_full_state["factory"]
    project_id = wave14_full_state["ids"]["project"]
    with factory() as session:
        candidate = session.scalar(
            sa.select(ContactCandidate)
            .where(ContactCandidate.project_id == project_id, ContactCandidate.is_current.is_(True))
            .order_by(ContactCandidate.rank.asc())
        )
        assert candidate is not None
        assert candidate.candidate_score is not None
    body = wave14_full_state["client"].get(f"/api/v1/projects/{project_id}/contact-candidates").json()
    assert body["items"][0]["display_name"] == "Doug Meadows"
    assert body["items"][0]["verification"]["project_association"] == "VERIFIED"
    assert body["items"][0]["verification"]["rental_authority"] == "UNKNOWN"


def test_pipeline_runs_have_stable_run_ids_and_ordered_events(wave14_full_state) -> None:
    factory = wave14_full_state["factory"]
    run_ids = {wave14_full_state["ids"]["stafford_run"], wave14_full_state["ids"]["ee_reed_run"]}
    assert len(run_ids) == 2
    with factory() as session:
        for run_id in run_ids:
            run = session.get(PipelineRun, run_id)
            assert run is not None and run.status.value == "SUCCEEDED"
            events = session.scalars(
                sa.select(PipelineEvent).where(PipelineEvent.pipeline_run_id == run_id).order_by(PipelineEvent.sequence_number)
            ).all()
            assert events
            assert [event.sequence_number for event in events] == list(range(1, len(events) + 1))
