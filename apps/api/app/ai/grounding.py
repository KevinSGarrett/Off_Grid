from __future__ import annotations

import re
from collections.abc import Iterable

from app.ai.evidence import EvidenceCatalog
from app.ai.schemas import GroundedClaim
from app.ai.types import GroundingIssue, GroundingReport, GroundingStatus
from app.domain.states import EvidenceClassification

_NUMERIC_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?")
_DETERMINISTIC_MATERIAL_RE = re.compile(
    r"\b(commercial fit|qualification|crm|pipedrive|deal[- ]ready|lead[- ]ready|"
    r"rental authority|product applicability|confirmed fit|next (?:best )?action)\b",
    re.IGNORECASE,
)


class GroundingValidator:
    """Deterministically reject AI claims that lack valid supporting evidence.

    The validator never accepts model confidence as proof. AI claims may be DERIVED, INFERRED,
    CONFLICTED or UNKNOWN; source truth/verification remains outside the model.
    """

    def __init__(self, catalog: EvidenceCatalog, *, high_risk_claim_types: Iterable[str] = ()):
        self.catalog = catalog
        self.high_risk_claim_types = {str(value) for value in high_risk_claim_types}

    def validate(self, claims: Iterable[GroundedClaim]) -> GroundingReport:
        valid: list[str] = []
        issues: list[GroundingIssue] = []
        conflicted = False
        for claim in claims:
            claim_issues = self._validate_claim(claim)
            if claim_issues:
                issues.extend(claim_issues)
            else:
                valid.append(claim.claim_id)
            if claim.classification == EvidenceClassification.CONFLICTED.value:
                conflicted = True
        if issues:
            status = GroundingStatus.UNSUPPORTED
        elif conflicted:
            status = GroundingStatus.CONFLICTED
        else:
            status = GroundingStatus.VALID
        return GroundingReport(status=status, valid_claim_ids=tuple(valid), issues=tuple(issues))

    def _validate_claim(self, claim: GroundedClaim) -> list[GroundingIssue]:
        issues: list[GroundingIssue] = []
        classification = claim.classification
        if classification == EvidenceClassification.UNKNOWN.value:
            # UNKNOWN may explicitly state that evidence is unavailable. It must not cite fake IDs.
            for ref in claim.evidence_ids:
                if self.catalog.get(ref) is None:
                    issues.append(GroundingIssue(claim.claim_id, f"unknown evidence id {ref}"))
            return issues

        if not claim.evidence_ids:
            return [GroundingIssue(claim.claim_id, "factual/inferred claim has no evidence ids")]

        evidence = []
        for ref in claim.evidence_ids:
            item = self.catalog.get(ref)
            if item is None:
                issues.append(GroundingIssue(claim.claim_id, f"unknown evidence id {ref}"))
            else:
                evidence.append(item)
        if issues:
            return issues

        if _DETERMINISTIC_MATERIAL_RE.search(claim.claim_text) and not any(
            ref.startswith("det:") for ref in claim.evidence_ids
        ):
            issues.append(
                GroundingIssue(
                    claim.claim_id,
                    "material workflow/assessment claim requires deterministic-state provenance",
                )
            )

        if claim.claim_type in self.high_risk_claim_types:
            corpus = " ".join(item.excerpt for item in evidence).lower()
            numbers = _NUMERIC_RE.findall(claim.claim_text)
            for number in numbers:
                normalized = number.replace(",", "")
                if number.lower() not in corpus and normalized.lower() not in corpus.replace(",", ""):
                    issues.append(
                        GroundingIssue(
                            claim.claim_id,
                            f"high-risk numeric assertion {number!r} is absent from cited evidence",
                        )
                    )
            if claim.claim_type == "rental_authority" and classification != EvidenceClassification.UNKNOWN.value:
                # A model may explain authority evidence but cannot itself convert it into verified authority.
                issues.append(
                    GroundingIssue(
                        claim.claim_id,
                        "AI cannot establish rental authority; direct verification state is deterministic",
                    )
                )
        return issues
