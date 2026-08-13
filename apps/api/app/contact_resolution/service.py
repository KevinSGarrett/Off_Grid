from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.contact_resolution.config import load_contact_resolution_configs
from app.contact_resolution.policy import SourcePrecedencePolicy
from app.contact_resolution.types import (
    ApolloPreviewPlan,
    ContactCandidateResult,
    ContactScoreFactor,
    EvidenceDecision,
    ContactResolutionResult,
)
from app.domain.states import (
    ConfidenceState,
    ContactPointType,
    ContactState,
    EvidenceClassification,
    IntegrationMode,
    MaskingPolicy,
    PIIClass,
    QualityFlagState,
    QualitySeverity,
    VerificationState,
)
from app.ingestion.normalization import normalized_name
from app.integrations.apollo import ApolloAdapter
from app.models import (
    ConfigVersion,
    ContactAssessment,
    ContactCandidate,
    ExternalEvidence,
    Organization,
    OrganizationAddress,
    OrganizationDomain,
    Person,
    PersonContactPoint,
    Project,
    ProjectPerson,
    QualityFlag,
    VerificationEvent,
)
from app.resolution.people import PersonResolutionService


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SNAPSHOT = ROOT / "research/WAVE_08_PUBLIC_RESEARCH_SNAPSHOT.json"


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _decimal(value: float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"))


class ContactResolutionService:
    """Turn bounded public research into evidence-backed contact candidates.

    This service deliberately separates employment, Stafford association, role relevance, and
    rental authority. Candidate rank answers "who should we investigate first?"; it never answers
    "who is the rental decision maker?" unless authority evidence is independently VERIFIED.
    """

    def __init__(self, session: Session, snapshot_path: str | Path = DEFAULT_SNAPSHOT):
        self.session = session
        self.configs = load_contact_resolution_configs()
        self.contact_config = self.configs.contact.data
        self.persona_config = self.configs.personas.data
        self.precedence = SourcePrecedencePolicy(self.configs.precedence.path)
        self.snapshot_path = Path(snapshot_path)
        if not self.snapshot_path.is_absolute():
            self.snapshot_path = ROOT / self.snapshot_path
        self.snapshot = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        self.retrieved_at = _parse_dt(self.snapshot["retrieved_at"])

    @property
    def version(self) -> str:
        return str(self.contact_config["model"]["version"])

    @property
    def persona_version(self) -> str:
        return str(self.persona_config["registry"]["version"])

    def run(self, *, project_external_id: str) -> ContactResolutionResult:
        project = self.session.scalar(sa.select(Project).where(Project.external_id == project_external_id))
        if project is None:
            raise ValueError(f"Project not found: {project_external_id}")

        self._persist_config("contact_resolution", self.version, self.configs.contact)
        self._persist_config("personas", self.persona_version, self.configs.personas)
        self._persist_config("source_precedence", self.precedence.version, self.configs.precedence)

        east_coast = self._ensure_east_coast_organization()
        self._persist_organization_evidence(project.id, east_coast.id)

        rows: list[ContactCandidateResult] = []
        for candidate_payload in self.snapshot["candidates"]:
            person = self._ensure_public_person(candidate_payload, east_coast.id)
            decisions = self._persist_candidate_evidence(project.id, person.id, east_coast.id, candidate_payload)
            row = self._upsert_candidate(project, person, east_coast, candidate_payload, decisions)
            rows.append(row)
            if candidate_payload.get("title_variance_note"):
                self._ensure_title_variance_flag(person.id, east_coast.id, candidate_payload["title_variance_note"])

        rows = self._assign_ranks(rows)
        self.session.flush()

        evidence_count = self.session.scalar(sa.select(sa.func.count()).select_from(ExternalEvidence)) or 0
        verification_count = self.session.scalar(sa.select(sa.func.count()).select_from(VerificationEvent)) or 0
        authority_count = self.session.scalar(
            sa.select(sa.func.count()).select_from(ContactAssessment).where(
                ContactAssessment.is_current.is_(True),
                ContactAssessment.rental_authority_state == VerificationState.VERIFIED,
            )
        ) or 0

        apollo_preview = self._apollo_preview(rows)
        self.session.commit()
        return ContactResolutionResult(
            contact_resolution_version=self.version,
            persona_version=self.persona_version,
            source_precedence_version=self.precedence.version,
            project_id=project.id,
            east_coast_organization_id=east_coast.id,
            candidates=tuple(rows),
            external_evidence_count=int(evidence_count),
            verification_event_count=int(verification_count),
            authority_verified_count=int(authority_count),
            apollo_preview=apollo_preview,
            explicit_unknowns=tuple(self.snapshot.get("explicit_unknowns", [])),
            research_snapshot_version=str(self.snapshot["snapshot_version"]),
        )

    def _persist_config(self, kind: str, version: str, loaded) -> ConfigVersion:
        existing = self.session.scalar(
            sa.select(ConfigVersion).where(ConfigVersion.config_kind == kind, ConfigVersion.version == version)
        )
        if existing is not None:
            if existing.content_sha256 != loaded.sha256:
                raise ValueError(f"{kind} version {version} was reused with changed content")
            return existing
        for row in self.session.scalars(
            sa.select(ConfigVersion).where(ConfigVersion.config_kind == kind, ConfigVersion.is_active.is_(True))
        ).all():
            row.is_active = False
        row = ConfigVersion(
            config_kind=kind,
            version=version,
            content_sha256=loaded.sha256,
            source_path=str(loaded.path),
            content_text=loaded.text,
            activated_at=datetime.now(timezone.utc),
            is_active=True,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _ensure_east_coast_organization(self) -> Organization:
        payload = self.snapshot["organization"]
        org = self.session.scalar(sa.select(Organization).where(Organization.canonical_key == payload["canonical_key"]))
        if org is None:
            org = Organization(
                canonical_name=payload["canonical_name"],
                normalized_name=payload["normalized_name"],
                canonical_key=payload["canonical_key"],
                organization_type="GENERAL_CONTRACTOR_OPERATING_COMPANY",
                status="ACTIVE",
                notes=(
                    "Public-source organization created separately from the ConstructConnect Houston source account. "
                    "Do not merge these records solely because they share the E.E. Reed family name."
                ),
            )
            self.session.add(org)
            self.session.flush()
        domain = str(payload["domain"]).lower()
        existing_domain = self.session.scalar(
            sa.select(OrganizationDomain).where(
                OrganizationDomain.organization_id == org.id,
                OrganizationDomain.normalized_domain == domain,
            )
        )
        if existing_domain is None:
            self.session.add(
                OrganizationDomain(
                    organization_id=org.id,
                    domain=domain,
                    normalized_domain=domain,
                    relationship_state=VerificationState.VERIFIED,
                    is_primary=True,
                )
            )
        address = payload["address"]
        normalized_address = normalized_name(
            " ".join(
                filter(
                    None,
                    [address.get("line1"), address.get("city"), address.get("region"), address.get("postal_code")],
                )
            )
        )
        exists_address = self.session.scalar(
            sa.select(OrganizationAddress).where(
                OrganizationAddress.organization_id == org.id,
                OrganizationAddress.normalized_address == normalized_address,
            )
        )
        if exists_address is None:
            self.session.add(
                OrganizationAddress(
                    organization_id=org.id,
                    address_type="OFFICE",
                    line1=address.get("line1"),
                    city=address.get("city"),
                    region=address.get("region"),
                    postal_code=address.get("postal_code"),
                    country_code=address.get("country_code"),
                    normalized_address=normalized_address,
                )
            )
        self.session.flush()
        return org

    def _persist_organization_evidence(self, project_id: UUID, organization_id: UUID) -> None:
        for item in self.snapshot.get("organization_evidence", []):
            subject_org = organization_id if item["attribute"] == "organization_identity" else None
            subject_project = project_id if item["attribute"] == "project_association" else None
            self._ensure_external_evidence(
                project_id=subject_project,
                organization_id=subject_org,
                person_id=None,
                item=item,
            )

    def _ensure_public_person(self, payload: dict, organization_id: UUID) -> Person:
        n = normalized_name(payload["name"])
        person = self.session.scalar(
            sa.select(Person).where(
                Person.normalized_name == n,
                Person.current_organization_id == organization_id,
            )
        )
        if person is None:
            parts = payload["name"].split()
            person = Person(
                display_name=payload["name"],
                normalized_name=n,
                given_name=parts[0] if parts else None,
                family_name=parts[-1] if len(parts) > 1 else None,
                current_organization_id=organization_id,
                employment_state=VerificationState.UNKNOWN,
                status="ACTIVE",
            )
            self.session.add(person)
            self.session.flush()
        return person

    def _persist_candidate_evidence(
        self,
        project_id: UUID,
        person_id: UUID,
        organization_id: UUID,
        payload: dict,
    ) -> dict[str, EvidenceDecision]:
        grouped: dict[str, list[tuple[ExternalEvidence, VerificationState]]] = {
            "employment": [],
            "project_association": [],
            "role_relevance": [],
            "rental_authority": [],
        }
        for item in payload.get("evidence", []):
            attribute = item["attribute"]
            evidence = self._ensure_external_evidence(
                project_id=project_id if attribute == "project_association" else None,
                organization_id=organization_id,
                person_id=person_id,
                item=item,
            )
            grouped.setdefault(attribute, []).append((evidence, evidence.verification_state))

        decisions: dict[str, EvidenceDecision] = {}
        for attribute in ("employment", "project_association", "role_relevance", "rental_authority"):
            evidence_rows = grouped.get(attribute, [])
            state, priority, source_types = self.precedence.aggregate(
                attribute,
                [(row.source_type, state) for row, state in evidence_rows],
            )
            ids = tuple(row.id for row, _ in evidence_rows)
            decisions[attribute] = EvidenceDecision(
                attribute=attribute,
                state=state,
                highest_priority=priority,
                evidence_ids=ids,
                source_types=source_types,
                rationale=self._dimension_rationale(attribute, state, source_types),
            )
            for row, _state in evidence_rows:
                self._ensure_verification_event(
                    person_id=person_id,
                    project_id=project_id,
                    dimension=attribute,
                    outcome=self.precedence.cap_state(row.verification_state, self.precedence.rule_for(attribute, row.source_type).max_state),
                    external_evidence_id=row.id,
                )
        return decisions

    def _ensure_external_evidence(
        self,
        *,
        project_id: UUID | None,
        organization_id: UUID | None,
        person_id: UUID | None,
        item: dict,
    ) -> ExternalEvidence:
        attribute = str(item["attribute"])
        requested = VerificationState(str(item.get("classification", "UNKNOWN")))
        rule = self.precedence.rule_for(attribute, str(item["source_type"]))
        state = self.precedence.cap_state(requested, rule.max_state)
        fingerprint_input = "|".join(
            [
                str(project_id or ""),
                str(organization_id or ""),
                str(person_id or ""),
                attribute,
                str(item["source_url"]),
                str(item["claim"]),
            ]
        )
        fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()
        existing = self.session.scalar(
            sa.select(ExternalEvidence).where(ExternalEvidence.evidence_fingerprint == fingerprint)
        )
        if existing is not None:
            return existing
        confidence_score = Decimal(rule.priority) / Decimal(100) if rule.priority else Decimal("0")
        if rule.priority >= 95:
            confidence_state = ConfidenceState.VERY_HIGH
        elif rule.priority >= 80:
            confidence_state = ConfidenceState.HIGH
        elif rule.priority >= 60:
            confidence_state = ConfidenceState.MEDIUM
        elif rule.priority > 0:
            confidence_state = ConfidenceState.LOW
        else:
            confidence_state = ConfidenceState.VERY_LOW
        row = ExternalEvidence(
            project_id=project_id,
            organization_id=organization_id,
            person_id=person_id,
            source_url=item["source_url"],
            source_title=item.get("source_title"),
            publisher=item.get("publisher"),
            source_type=item["source_type"],
            claim=item["claim"],
            evidence_fingerprint=fingerprint,
            classification=(
                EvidenceClassification.VERIFIED
                if state is VerificationState.VERIFIED
                else EvidenceClassification.DERIVED
                if state is VerificationState.SUPPORTED
                else EvidenceClassification.UNKNOWN
            ),
            verification_state=state,
            confidence_state=confidence_state,
            confidence_score=confidence_score,
            retrieved_at=self.retrieved_at,
            pii_class=PIIClass.PUBLIC_BUSINESS,
            demo_masking_policy=MaskingPolicy.NONE,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _ensure_verification_event(
        self,
        *,
        person_id: UUID,
        project_id: UUID,
        dimension: str,
        outcome: VerificationState,
        external_evidence_id: UUID,
    ) -> VerificationEvent:
        existing = self.session.scalar(
            sa.select(VerificationEvent).where(
                VerificationEvent.person_id == person_id,
                VerificationEvent.project_id == project_id,
                VerificationEvent.dimension == dimension,
                VerificationEvent.external_evidence_id == external_evidence_id,
                VerificationEvent.verification_type == "PUBLIC_WEB_RESEARCH",
            )
        )
        if existing is not None:
            return existing
        row = VerificationEvent(
            person_id=person_id,
            project_id=project_id,
            dimension=dimension,
            verification_type="PUBLIC_WEB_RESEARCH",
            outcome=outcome,
            external_evidence_id=external_evidence_id,
            note="Bounded public research snapshot; no prospect outreach performed.",
            verified_by="public_research_snapshot",
            verified_at=self.retrieved_at,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _upsert_candidate(
        self,
        project: Project,
        person: Person,
        organization: Organization,
        payload: dict,
        decisions: dict[str, EvidenceDecision],
    ) -> ContactCandidateResult:
        employment = decisions["employment"].state
        project_association = decisions["project_association"].state
        role_relevance = decisions["role_relevance"].state
        rental_authority = decisions["rental_authority"].state

        person.employment_state = employment
        state = self._contact_state(employment, project_association, role_relevance, rental_authority)
        factors = self._score_factors(project, person, decisions)
        score = sum((factor.points for factor in factors), Decimal("0.000"))

        candidate = self.session.scalar(
            sa.select(ContactCandidate).where(
                ContactCandidate.project_id == project.id,
                ContactCandidate.person_id == person.id,
            )
        )
        rationale = {
            "public_role_label": payload["public_role_label"],
            "employment": employment.value,
            "project_association": project_association.value,
            "role_relevance": role_relevance.value,
            "rental_authority": rental_authority.value,
            "warning": "Candidate score ranks investigation priority only; it does not verify rental authority.",
        }
        if candidate is None:
            candidate = ContactCandidate(
                project_id=project.id,
                person_id=person.id,
                organization_id=organization.id,
            )
            self.session.add(candidate)
            self.session.flush()
        candidate.state = state
        candidate.candidate_score = score
        candidate.target_persona = payload["target_persona"]
        candidate.rationale = json.dumps(rationale, sort_keys=True)
        candidate.is_current = True

        assessment = self.session.scalar(
            sa.select(ContactAssessment).where(
                ContactAssessment.candidate_id == candidate.id,
                ContactAssessment.is_current.is_(True),
            )
        )
        explanation = json.dumps(
            {
                "dimensions": rationale,
                "score_factors": [
                    {"key": factor.key, "points": str(factor.points), "max_points": str(factor.max_points), "rationale": factor.rationale}
                    for factor in factors
                ],
            },
            sort_keys=True,
        )
        if assessment is None:
            assessment = ContactAssessment(
                candidate_id=candidate.id,
                employment_state=employment,
                project_association_state=project_association,
                role_relevance_state=role_relevance,
                rental_authority_state=rental_authority,
                assessed_at=self.retrieved_at,
                explanation=explanation,
                is_current=True,
            )
            self.session.add(assessment)
        else:
            assessment.employment_state = employment
            assessment.project_association_state = project_association
            assessment.role_relevance_state = role_relevance
            assessment.rental_authority_state = rental_authority
            assessment.assessed_at = self.retrieved_at
            assessment.explanation = explanation

        if project_association in {VerificationState.SUPPORTED, VerificationState.VERIFIED}:
            existing_project_person = self.session.scalar(
                sa.select(ProjectPerson).where(
                    ProjectPerson.project_id == project.id,
                    ProjectPerson.person_id == person.id,
                    ProjectPerson.role == payload["public_role_label"],
                )
            )
            if existing_project_person is None:
                self.session.add(
                    ProjectPerson(
                        project_id=project.id,
                        person_id=person.id,
                        organization_id=organization.id,
                        role=payload["public_role_label"],
                        association_state=project_association,
                    )
                )
            else:
                existing_project_person.association_state = project_association
        self.session.flush()

        evidence_ids = tuple(
            sorted(
                {eid for decision in decisions.values() for eid in decision.evidence_ids},
                key=str,
            )
        )
        recommended_action = (
            "Verify temporary-lighting/mobile-power responsibility and rental authority directly; do not treat this candidate as a confirmed decision maker."
            if project_association is VerificationState.VERIFIED
            else "Establish Stafford-specific project association before selected-candidate enrichment or authority verification."
        )
        return ContactCandidateResult(
            candidate_id=candidate.id,
            person_id=person.id,
            person_name=person.display_name,
            organization_id=organization.id,
            organization_name=organization.canonical_name,
            target_persona=payload["target_persona"],
            public_role_label=payload["public_role_label"],
            rank=0,
            candidate_score=score,
            state=state,
            employment_state=employment,
            project_association_state=project_association,
            role_relevance_state=role_relevance,
            rental_authority_state=rental_authority,
            score_factors=tuple(factors),
            evidence_ids=evidence_ids,
            recommended_action=recommended_action,
        )

    def _score_factors(self, project: Project, person: Person, decisions: dict[str, EvidenceDecision]) -> list[ContactScoreFactor]:
        weights = self.contact_config["score_weights"]
        state_scores = self.contact_config["verification_state_scores"]

        def verification_factor(key: str, dimension: str) -> ContactScoreFactor:
            max_points = _decimal(weights[key])
            state = decisions[dimension].state
            multiplier = Decimal(str(state_scores.get(state.value, 0)))
            return ContactScoreFactor(
                key=key,
                points=(max_points * multiplier).quantize(Decimal("0.001")),
                max_points=max_points,
                rationale=f"{dimension}={state.value}; source precedence applied per attribute.",
            )

        factors = [
            verification_factor("project_association", "project_association"),
            verification_factor("role_relevance", "role_relevance"),
            verification_factor("employment", "employment"),
        ]

        freshness_cfg = self.contact_config["freshness"]
        age_days = max((datetime.now(timezone.utc) - self.retrieved_at).days, 0)
        freshness_max = _decimal(weights["source_freshness"])
        if age_days <= int(freshness_cfg["full_score_days"]):
            freshness_points = freshness_max
        elif age_days <= int(freshness_cfg["partial_score_days"]):
            freshness_points = (freshness_max * Decimal(str(freshness_cfg["partial_multiplier"]))).quantize(Decimal("0.001"))
        else:
            freshness_points = Decimal("0.000")
        factors.append(
            ContactScoreFactor(
                key="source_freshness",
                points=freshness_points,
                max_points=freshness_max,
                rationale=f"Public evidence snapshot age={age_days} days.",
            )
        )

        contact_points = self.session.scalars(
            sa.select(PersonContactPoint).where(
                PersonContactPoint.person_id == person.id,
                PersonContactPoint.contact_type.in_([ContactPointType.EMAIL, ContactPointType.PHONE]),
            )
        ).all()
        contactability_max = _decimal(weights["direct_contactability"])
        if any(cp.verification_state is VerificationState.VERIFIED and not cp.is_generic for cp in contact_points):
            contactability_points = contactability_max
            contactability_reason = "Verified direct business contact exists."
        elif any(cp.verification_state is VerificationState.SUPPORTED and not cp.is_generic for cp in contact_points):
            contactability_points = (contactability_max * Decimal("0.7")).quantize(Decimal("0.001"))
            contactability_reason = "Supported direct business contact exists."
        else:
            contactability_points = Decimal("0.000")
            contactability_reason = "No verified direct business email/phone is stored; public office routing is not treated as person-level contact proof."
        factors.append(
            ContactScoreFactor(
                key="direct_contactability",
                points=contactability_points,
                max_points=contactability_max,
                rationale=contactability_reason,
            )
        )

        recurrence_max = _decimal(weights["account_recurrence"])
        source_org = self.session.scalar(
            sa.select(Organization).where(Organization.canonical_key == "constructconnect:company:1000647848")
        )
        recurrence_count = 0
        if source_org is not None:
            for signal in PersonResolutionService(self.session).recurrence_signals(source_org.id):
                if normalized_name(signal.person_name) == person.normalized_name:
                    recurrence_count = signal.unique_project_count
                    break
        full_projects = int(self.contact_config["recurrence"]["projects_for_full_score"])
        recurrence_multiplier = min(Decimal(recurrence_count) / Decimal(full_projects), Decimal("1")) if recurrence_count else Decimal("0")
        factors.append(
            ContactScoreFactor(
                key="account_recurrence",
                points=(recurrence_max * recurrence_multiplier).quantize(Decimal("0.001")),
                max_points=recurrence_max,
                rationale=(
                    f"ConstructConnect source recurrence={recurrence_count} unique projects; recurrence is context only and never proves Stafford authority."
                ),
            )
        )
        return factors

    def _contact_state(
        self,
        employment: VerificationState,
        project_association: VerificationState,
        role_relevance: VerificationState,
        rental_authority: VerificationState,
    ) -> ContactState:
        state = ContactState.DISCOVERED
        if employment is not VerificationState.VERIFIED:
            return state
        state = ContactState.EMPLOYMENT_VERIFIED
        if project_association is not VerificationState.VERIFIED:
            return state
        state = ContactState.PROJECT_ASSOCIATION_VERIFIED
        if role_relevance not in {VerificationState.VERIFIED, VerificationState.SUPPORTED}:
            return state
        state = ContactState.ROLE_RELEVANT
        if rental_authority is VerificationState.VERIFIED:
            state = ContactState.AUTHORITY_VERIFIED
        return state

    def _assign_ranks(self, rows: list[ContactCandidateResult]) -> list[ContactCandidateResult]:
        ordered = sorted(rows, key=lambda row: (-row.candidate_score, row.person_name.lower()))
        ranked: list[ContactCandidateResult] = []
        for index, row in enumerate(ordered, start=1):
            candidate = self.session.get(ContactCandidate, row.candidate_id)
            if candidate is not None:
                candidate.rank = index
            ranked.append(
                ContactCandidateResult(
                    **{**row.__dict__, "rank": index},
                )
            )
        return ranked

    def _apollo_preview(self, rows: list[ContactCandidateResult]) -> ApolloPreviewPlan:
        title_set: list[str] = []
        for persona in self.persona_config["personas"]:
            if persona.get("priority") in {"HIGH", "SECONDARY"}:
                title_set.extend(persona.get("titles", []))
        titles = sorted(set(title_set))
        adapter = ApolloAdapter(mode=IntegrationMode.PREVIEW)
        search = adapter.preview_search(
            titles=titles,
            domains=[self.snapshot["organization"]["domain"]],
            person_locations=["Virginia"],
            per_page=25,
        )
        selected = tuple(row.candidate_id for row in rows[:3])
        return ApolloPreviewPlan(
            mode=search.mode.value,
            search_endpoint=search.endpoint,
            search_payload=search.params,
            enrichment_endpoint=adapter.ENRICH_ENDPOINT,
            enrichment_candidate_ids=selected,
            notes=(
                "No Apollo network call was executed during contact resolution.",
                "People Search is previewed first; only selected high-value candidates would be enriched.",
                "Rental authority remains an independent verification dimension even after enrichment.",
            ),
        )

    def _ensure_title_variance_flag(self, person_id: UUID, organization_id: UUID, note: str) -> QualityFlag:
        existing = self.session.scalar(
            sa.select(QualityFlag).where(
                QualityFlag.rule_code == "PUBLIC_ROLE_TITLE_VARIANCE",
                QualityFlag.person_id == person_id,
                QualityFlag.state == QualityFlagState.OPEN,
            )
        )
        if existing is not None:
            return existing
        row = QualityFlag(
            rule_code="PUBLIC_ROLE_TITLE_VARIANCE",
            severity=QualitySeverity.LOW,
            state=QualityFlagState.OPEN,
            organization_id=organization_id,
            person_id=person_id,
            title="Public role-title wording varies across current first-party sources",
            detail=note,
            decision_impact="LOW",
            blocks_progression=False,
            first_detected_at=self.retrieved_at,
        )
        self.session.add(row)
        self.session.flush()
        return row

    @staticmethod
    def _dimension_rationale(attribute: str, state: VerificationState, source_types: tuple[str, ...]) -> str:
        if not source_types:
            return f"{attribute} remains UNKNOWN because no qualifying evidence exists in the bounded research snapshot."
        return f"{attribute}={state.value} after attribute-specific source precedence across {', '.join(source_types)}."
