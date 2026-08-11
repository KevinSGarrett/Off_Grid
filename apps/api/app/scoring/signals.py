from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import EvidenceClassification, ValidationState, VerificationState
from app.models import Project, ProjectOrganization, ProjectSignal, QualityFlag, SourceObservation
from app.scoring.types import SignalSnapshot


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _text(obs: SourceObservation | None) -> str:
    if obs is None:
        return ""
    return (obs.normalized_text or obs.raw_value or "").lower()


class ProjectSignalBuilder:
    """Create explainable deterministic/derived project signals from normalized source state.

    This builder intentionally contains no project-name or project-ID special cases. Signal rules are
    source-shape/business semantics that can run over any project with the same normalized fields.
    """

    def __init__(self, session: Session):
        self.session = session

    def build(self, project: Project, *, persist: bool = True) -> dict[str, SignalSnapshot]:
        observations = self.session.scalars(
            sa.select(SourceObservation)
            .where(SourceObservation.project_id == project.id)
            .order_by(SourceObservation.created_at.desc())
        ).all()
        by_field: dict[str, list[SourceObservation]] = {}
        for obs in observations:
            by_field.setdefault(obs.field_name, []).append(obs)

        def latest(field: str) -> SourceObservation | None:
            rows = by_field.get(field, [])
            return rows[0] if rows else None

        scope = latest("project.scope")
        description = latest("project.description")
        notes = latest("project.notes")
        stage = latest("project.stage")
        value = latest("project.reported_value")
        start_date = latest("project.start_date")
        combined = " ".join(_text(x) for x in (scope, description, notes))

        signals: dict[str, SignalSnapshot] = {}

        def add(
            key: str,
            present: bool,
            classification: EvidenceClassification,
            confidence: Decimal | None,
            eligible: bool,
            explanation: str,
            source: SourceObservation | None = None,
        ) -> None:
            snapshot = SignalSnapshot(
                key=key,
                present=present,
                classification=classification,
                confidence_score=confidence,
                decision_eligible=eligible,
                explanation=explanation,
                source_observation_id=source.id if source else None,
            )
            signals[key] = snapshot
            if persist:
                self._upsert_signal(project.id, snapshot)

        source_decision = lambda obs: bool(obs and getattr(obs, "decision_eligible", False))
        high = _decimal("0.95")

        add("data_center", "data center" in combined, EvidenceClassification.EXPLICIT, high, source_decision(scope) or source_decision(description), "Source narrative explicitly identifies data-center construction.", scope or description)
        add("new_construction", "new construction" in combined or (project.stage or "").lower() == "new", EvidenceClassification.EXPLICIT, high, source_decision(scope) or source_decision(notes), "Source scope/notes identify new construction.", scope or notes)
        add("site_work", "site work" in combined, EvidenceClassification.EXPLICIT, high, source_decision(scope) or source_decision(notes), "Source scope/notes explicitly identify site work.", scope or notes)
        add("paving", "paving" in combined, EvidenceClassification.EXPLICIT, high, source_decision(scope) or source_decision(notes), "Source scope/notes explicitly identify paving.", scope or notes)
        add("multi_phase", "multi-phas" in combined or "phases" in (project.canonical_name or "").lower(), EvidenceClassification.EXPLICIT, _decimal("0.90"), source_decision(description) or source_decision(scope), "Source narrative/name identifies a multi-phase development context.", description or scope)
        add("related_phases_underway", "phases 1 & 2 are underway" in combined, EvidenceClassification.EXPLICIT, _decimal("0.90"), source_decision(description), "Source narrative states related earlier phases are underway.", description)
        add("large_development", any(token in combined for token in ("$10 billion", "20 data center", "5.5 million")), EvidenceClassification.DERIVED, _decimal("0.75"), source_decision(description), "Qualitative large-development signal derived from source-described broader campus scale; exact projections are not treated as verified phase quantities.", description)

        gc_rows = self.session.scalars(
            sa.select(ProjectOrganization).where(
                ProjectOrganization.project_id == project.id,
                ProjectOrganization.role == "General Contractor",
            )
        ).all()
        gc_identified = bool(gc_rows)
        gc_supported = any(row.verification_state in {VerificationState.SUPPORTED, VerificationState.VERIFIED} for row in gc_rows)
        gc_obs = None
        for row in gc_rows:
            if row.source_observation_id:
                gc_obs = self.session.get(SourceObservation, row.source_observation_id)
                break
        add("general_contractor_identified", gc_identified, EvidenceClassification.EXPLICIT, _decimal("0.95") if gc_supported else _decimal("0.50"), source_decision(gc_obs), "A General Contractor relationship is present in canonical project relationships.", gc_obs)
        stage_text = _text(stage)
        add("gc_awarded", "general contractor award" in stage_text, EvidenceClassification.EXPLICIT, stage.confidence_score if stage else None, source_decision(stage), "Source stage explicitly indicates General Contractor Award.", stage)

        flags = {row.rule_code for row in self.session.scalars(sa.select(QualityFlag).where(QualityFlag.project_id == project.id)).all()}
        trusted_timing = bool(start_date and start_date.validation_state is ValidationState.VALID and getattr(start_date, "decision_eligible", False))
        add("trusted_start_timing", trusted_timing, EvidenceClassification.DERIVED, start_date.confidence_score if start_date else None, trusted_timing, "Start timing is usable only when the source date semantics validate cleanly.", start_date)
        large_value = bool(value and value.normalized_decimal is not None and value.normalized_decimal >= Decimal("100000000"))
        value_eligible = bool(value and getattr(value, "decision_eligible", False))
        add("large_project_value", large_value, EvidenceClassification.EXPLICIT, value.confidence_score if value else None, value_eligible, "Reported project value exceeds the scale threshold, but its scoring contribution is capped by configuration/source treatment.", value)
        add("project_value_verified", bool(value and value.validation_state is ValidationState.VALID and value.confidence_score and value.confidence_score >= Decimal("0.85")), EvidenceClassification.DERIVED, value.confidence_score if value else None, False, "Value is only considered verified enough when validation and trust clear the configured evidence bar.", value)

        named_gc_contact = "MISSING_PROJECT_GC_CONTACT" not in flags
        add("named_gc_project_contact", named_gc_contact, EvidenceClassification.DERIVED, _decimal("0.80") if named_gc_contact else _decimal("0.20"), named_gc_contact, "Presence/absence is derived from the project-level GC contact completeness quality rule.", gc_obs)
        # A generic organization inbox is intentionally not treated as a meaningful project-person channel.
        add("gc_contact_channel", False, EvidenceClassification.UNKNOWN, None, False, "No verified project-person contact channel is established in the supplied project record.", gc_obs)

        outdoor = signals["site_work"].present and signals["paving"].present
        outdoor_eligible = signals["site_work"].decision_eligible and signals["paving"].decision_eligible
        add("outdoor_site_activity", outdoor, EvidenceClassification.DERIVED, _decimal("0.85") if outdoor else None, outdoor_eligible, "Outdoor/distributed site activity is derived from explicit site-work and paving evidence.", scope)

        # Commercial-use-case hypotheses remain explicitly INFERRED and not eligible for deterministic qualification.
        lighting_inference = signals["site_work"].present and signals["new_construction"].present
        add("temporary_lighting_relevance", lighting_inference, EvidenceClassification.INFERRED, _decimal("0.65") if lighting_inference else None, False, "Temporary lighting relevance is a commercial inference requiring validation; it is not a source fact.", scope)
        power_inference = signals["large_development"].present and signals["new_construction"].present
        add("temporary_power_relevance", power_inference, EvidenceClassification.INFERRED, _decimal("0.55") if power_inference else None, False, "Temporary/mobile power relevance is a commercial inference requiring validation; no power demand is confirmed.", description or scope)

        return signals

    def _upsert_signal(self, project_id: UUID, snapshot: SignalSnapshot) -> None:
        stmt = sa.select(ProjectSignal).where(
            ProjectSignal.project_id == project_id,
            ProjectSignal.signal_key == snapshot.key,
        )
        existing = self.session.scalar(stmt.order_by(ProjectSignal.created_at.desc()))
        if existing is None:
            existing = ProjectSignal(project_id=project_id, signal_key=snapshot.key, classification=snapshot.classification)
            self.session.add(existing)
        existing.signal_value = "true" if snapshot.present else "false"
        existing.classification = snapshot.classification
        existing.confidence_score = snapshot.confidence_score
        existing.source_observation_id = snapshot.source_observation_id
        existing.explanation = snapshot.explanation
        self.session.flush()
