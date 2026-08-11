from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.states import PIIClass
from app.models import ExternalEvidence, SourceEvidence, SourceObservation
from app.ai.types import EvidenceItem


class EvidenceCatalog:
    """Read-only evidence lookup and data-minimized packet builder."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def source_ref(evidence_id: UUID) -> str:
        return f"src:{evidence_id}"

    @staticmethod
    def external_ref(evidence_id: UUID) -> str:
        return f"ext:{evidence_id}"

    def get(self, evidence_ref: str) -> EvidenceItem | None:
        prefix, _, raw_id = evidence_ref.partition(":")
        try:
            evidence_id = UUID(raw_id)
        except (ValueError, TypeError):
            return None
        if prefix == "src":
            row = self.session.get(SourceEvidence, evidence_id)
            if row is None:
                return None
            return EvidenceItem(
                evidence_id=evidence_ref,
                excerpt=row.excerpt,
                source_kind="source",
                page_number=row.page_number,
                classification=row.classification.value,
                pii_class=row.pii_class.value,
            )
        if prefix == "ext":
            row = self.session.get(ExternalEvidence, evidence_id)
            if row is None:
                return None
            return EvidenceItem(
                evidence_id=evidence_ref,
                excerpt=row.claim,
                source_kind="external",
                classification=row.classification.value,
                pii_class=row.pii_class.value,
            )
        return None

    def project_packet(
        self,
        project_id: UUID,
        *,
        limit: int = 24,
        excerpt_chars: int = 700,
        include_business_contact_pii: bool = False,
    ) -> tuple[EvidenceItem, ...]:
        stmt = (
            sa.select(SourceEvidence)
            .join(SourceObservation, SourceEvidence.observation_id == SourceObservation.id)
            .where(
                SourceObservation.project_id == project_id,
                SourceEvidence.is_permitted_for_decision.is_(True),
            )
            .order_by(SourceEvidence.page_number.asc().nulls_last(), SourceEvidence.created_at.asc())
            .limit(limit)
        )
        rows = self.session.scalars(stmt).all()
        packet: list[EvidenceItem] = []
        for row in rows:
            if not include_business_contact_pii and row.pii_class is not PIIClass.NONE:
                continue
            packet.append(
                EvidenceItem(
                    evidence_id=self.source_ref(row.id),
                    excerpt=row.excerpt[:excerpt_chars],
                    source_kind="source",
                    page_number=row.page_number,
                    classification=row.classification.value,
                    pii_class=row.pii_class.value,
                )
            )
        return tuple(packet)

    def existing_refs(self, refs: Iterable[str]) -> set[str]:
        return {ref for ref in refs if self.get(ref) is not None}
