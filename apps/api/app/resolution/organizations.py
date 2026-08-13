from __future__ import annotations

import re
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.domain.states import QualitySeverity, VerificationState
from app.ingestion.normalization import normalized_name
from app.models import (
    Organization,
    OrganizationAddress,
    OrganizationAlias,
    OrganizationDomain,
    QualityFlag,
)
from app.resolution.types import MatchDecision

_HQ_SUFFIX_RE = re.compile(r"\s*-\s*[^-()]+\s*\(HQ\)\s*$", re.I)


def canonicalize_organization_label(label: str) -> str:
    """Conservatively remove source-display location/HQ decoration, not legal/division wording."""
    cleaned = _HQ_SUFFIX_RE.sub("", label).strip(" -")
    return cleaned or label.strip()


def _domain_set(session: Session, organization_id: UUID, *, supported_only: bool = False) -> set[str]:
    stmt = sa.select(OrganizationDomain).where(OrganizationDomain.organization_id == organization_id)
    rows = session.scalars(stmt).all()
    if supported_only:
        rows = [row for row in rows if row.relationship_state in {VerificationState.SUPPORTED, VerificationState.VERIFIED}]
    return {row.normalized_domain for row in rows}


def _address_set(session: Session, organization_id: UUID) -> set[str]:
    rows = session.scalars(
        sa.select(OrganizationAddress).where(OrganizationAddress.organization_id == organization_id)
    ).all()
    return {row.normalized_address for row in rows if row.normalized_address}


def _alias_set(session: Session, organization_id: UUID) -> set[str]:
    rows = session.scalars(
        sa.select(OrganizationAlias).where(OrganizationAlias.organization_id == organization_id)
    ).all()
    return {row.normalized_alias for row in rows}


class OrganizationResolutionService:
    def __init__(self, session: Session):
        self.session = session

    def canonicalize_source_account(self, organization_id: UUID) -> MatchDecision:
        org = self.session.get(Organization, organization_id)
        if org is None:
            raise ValueError(f"Organization not found: {organization_id}")
        source_label = org.canonical_name
        canonical = canonicalize_organization_label(source_label)
        if canonical != source_label:
            self._ensure_alias(org, source_label, alias_type="SOURCE_LABEL")
            org.canonical_name = canonical
            org.normalized_name = normalized_name(canonical)
            self._ensure_alias(org, canonical, alias_type="CANONICAL_NORMALIZATION")
        else:
            self._ensure_alias(org, source_label, alias_type="SOURCE_LABEL")

        ambiguity = self.domain_ambiguity(org.id)
        if ambiguity:
            self._ensure_quality_flag(
                org,
                code="ORGANIZATION_DIVISION_AMBIGUITY",
                severity=QualitySeverity.HIGH,
                title="Organization/division relationship remains unresolved",
                detail=(
                    "The source account contains multiple domains with unresolved relationship states. "
                    "Canonicalizing the source label does not prove that Houston, East Coast, or another affiliate/division is the operating Stafford entity."
                ),
            )
        self.session.flush()
        return MatchDecision(
            subject_id=org.id,
            candidate_id=org.id,
            decision="CANONICALIZED_SOURCE_ACCOUNT",
            score=Decimal("1.0000"),
            method="SOURCE_COMPANY_ID_PLUS_CONSERVATIVE_LABEL_NORMALIZATION",
            deterministic=True,
            rationale=(
                "The ConstructConnect company ID remains the stable source-account identity. The display suffix '- Houston (HQ)' "
                "is preserved as an alias while the canonical label becomes 'EE Reed Construction'."
            ),
            review_required=ambiguity,
        )

    def compare(self, subject: Organization, candidate: Organization) -> MatchDecision:
        if subject.id == candidate.id:
            return MatchDecision(
                subject_id=subject.id,
                candidate_id=candidate.id,
                decision="SAME_RECORD",
                score=Decimal("1.0000"),
                method="PRIMARY_KEY",
                deterministic=True,
                rationale="Same canonical Organization row.",
                review_required=False,
            )
        if subject.canonical_key == candidate.canonical_key:
            return MatchDecision(
                subject_id=subject.id,
                candidate_id=candidate.id,
                decision="AUTO_MATCH",
                score=Decimal("1.0000"),
                method="CANONICAL_KEY",
                deterministic=True,
                rationale="Organizations share the same canonical source key.",
                review_required=False,
            )

        subject_names = {subject.normalized_name, *_alias_set(self.session, subject.id)}
        candidate_names = {candidate.normalized_name, *_alias_set(self.session, candidate.id)}
        if subject_names & candidate_names:
            return MatchDecision(
                subject_id=subject.id,
                candidate_id=candidate.id,
                decision="AUTO_MATCH",
                score=Decimal("0.9800"),
                method="EXACT_NORMALIZED_ALIAS",
                deterministic=True,
                rationale="An exact normalized canonical name/alias is shared.",
                review_required=False,
            )

        supported_domain_overlap = _domain_set(self.session, subject.id, supported_only=True) & _domain_set(
            self.session, candidate.id, supported_only=True
        )
        if supported_domain_overlap:
            name_score = fuzz.token_set_ratio(subject.normalized_name, candidate.normalized_name)
            if name_score >= 80:
                return MatchDecision(
                    subject_id=subject.id,
                    candidate_id=candidate.id,
                    decision="AUTO_MATCH",
                    score=Decimal("0.9600"),
                    method="SUPPORTED_DOMAIN_PLUS_NAME",
                    deterministic=True,
                    rationale=f"Supported domain overlap ({', '.join(sorted(supported_domain_overlap))}) plus compatible names.",
                    review_required=False,
                )

        address_overlap = _address_set(self.session, subject.id) & _address_set(self.session, candidate.id)
        if address_overlap:
            name_score = fuzz.token_set_ratio(subject.normalized_name, candidate.normalized_name)
            if name_score >= 85:
                return MatchDecision(
                    subject_id=subject.id,
                    candidate_id=candidate.id,
                    decision="AUTO_MATCH",
                    score=Decimal("0.9400"),
                    method="EXACT_ADDRESS_PLUS_NAME",
                    deterministic=True,
                    rationale="Normalized address is identical and names are strongly compatible.",
                    review_required=False,
                )

        # Unknown/unverified domain overlap is never enough for automatic identity.
        any_domain_overlap = _domain_set(self.session, subject.id) & _domain_set(self.session, candidate.id)
        fuzzy_score = fuzz.token_set_ratio(subject.normalized_name, candidate.normalized_name)
        if any_domain_overlap or fuzzy_score >= 90:
            reasons: list[str] = []
            if any_domain_overlap:
                reasons.append(f"unverified domain overlap: {', '.join(sorted(any_domain_overlap))}")
            if fuzzy_score >= 90:
                reasons.append(f"name similarity {fuzzy_score}%")
            return MatchDecision(
                subject_id=subject.id,
                candidate_id=candidate.id,
                decision="REVIEW",
                score=Decimal(str(round(fuzzy_score / 100, 4))),
                method="FUZZY_OR_UNVERIFIED_DOMAIN",
                deterministic=False,
                rationale="; ".join(reasons) + ". Fuzzy or unverified-domain evidence cannot silently merge organizations.",
                review_required=True,
            )
        return MatchDecision(
            subject_id=subject.id,
            candidate_id=candidate.id,
            decision="NO_MATCH",
            score=Decimal(str(round(fuzzy_score / 100, 4))),
            method="FUZZY_NAME",
            deterministic=False,
            rationale="No deterministic identity evidence and fuzzy similarity is below the review threshold.",
            review_required=False,
        )

    def domain_ambiguity(self, organization_id: UUID) -> bool:
        rows = self.session.scalars(
            sa.select(OrganizationDomain).where(OrganizationDomain.organization_id == organization_id)
        ).all()
        if len(rows) <= 1:
            return False
        return any(row.relationship_state is VerificationState.UNKNOWN for row in rows)

    def _ensure_alias(self, org: Organization, alias: str, *, alias_type: str) -> OrganizationAlias:
        norm = normalized_name(alias)
        row = self.session.scalar(
            sa.select(OrganizationAlias).where(
                OrganizationAlias.organization_id == org.id,
                OrganizationAlias.normalized_alias == norm,
            )
        )
        if row is None:
            row = OrganizationAlias(
                organization_id=org.id,
                alias=alias,
                normalized_alias=norm,
                alias_type=alias_type,
            )
            self.session.add(row)
            self.session.flush()
        elif not row.alias_type:
            row.alias_type = alias_type
        return row

    def _ensure_quality_flag(
        self,
        org: Organization,
        *,
        code: str,
        severity: QualitySeverity,
        title: str,
        detail: str,
    ) -> None:
        existing = self.session.scalar(
            sa.select(QualityFlag).where(
                QualityFlag.organization_id == org.id,
                QualityFlag.rule_code == code,
            )
        )
        if existing is None:
            from datetime import datetime, timezone

            self.session.add(
                QualityFlag(
                    rule_code=code,
                    severity=severity,
                    organization_id=org.id,
                    title=title,
                    detail=detail,
                    decision_impact="HIGH",
                    blocks_progression=False,
                    first_detected_at=datetime.now(timezone.utc),
                )
            )
