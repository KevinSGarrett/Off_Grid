from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ai.evidence import EvidenceCatalog
from app.models import (
    ContactAssessment,
    ContactCandidate,
    CRMRecord,
    CRMSyncAttempt,
    ExternalEvidence,
    NextAction,
    OpportunityAssessment,
    Organization,
    Person,
    ProductFitAssessment,
    Project,
)


@dataclass(frozen=True, slots=True)
class ReadOnlyTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Mapping[str, Any]]

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }


_UUID_PARAMETER = {
    "type": "object",
    "properties": {"id": {"type": "string", "description": "Canonical UUID identifier."}},
    "required": ["id"],
    "additionalProperties": False,
}

_PROJECT_PARAMETER = {
    "type": "object",
    "properties": {
        "project_id": {"type": "string", "description": "Canonical project UUID."}
    },
    "required": ["project_id"],
    "additionalProperties": False,
}


class ReadOnlyCommercialToolRegistry:
    """Approved Commercial Analyst tools. Every handler is read-only and returns JSON-safe data."""

    def __init__(self, session: Session):
        self.session = session
        self.evidence = EvidenceCatalog(session)
        self._tools = self._build_tools()

    def _build_tools(self) -> dict[str, ReadOnlyTool]:
        return {
            "get_project": ReadOnlyTool(
                "get_project",
                "Return canonical project identity, stage, geography and source identifier.",
                _PROJECT_PARAMETER,
                self._get_project,
            ),
            "get_project_evidence": ReadOnlyTool(
                "get_project_evidence",
                "Return data-minimized evidence excerpts and evidence IDs for a project.",
                _PROJECT_PARAMETER,
                self._get_project_evidence,
            ),
            "get_project_assessment": ReadOnlyTool(
                "get_project_assessment",
                "Return the current deterministic Commercial Fit and Data Confidence assessment.",
                _PROJECT_PARAMETER,
                self._get_project_assessment,
            ),
            "get_product_fit": ReadOnlyTool(
                "get_product_fit",
                "Return current deterministic KVT/KV6/KVP product-fit assessments.",
                _PROJECT_PARAMETER,
                self._get_product_fit,
            ),
            "get_account": ReadOnlyTool(
                "get_account",
                "Return canonical organization identity without raw contact details.",
                _UUID_PARAMETER,
                self._get_account,
            ),
            "get_contact_candidates": ReadOnlyTool(
                "get_contact_candidates",
                "Return ranked contact candidates and independent verification dimensions, without email/phone.",
                _PROJECT_PARAMETER,
                self._get_contact_candidates,
            ),
            "get_contact_evidence": ReadOnlyTool(
                "get_contact_evidence",
                "Return stored public/research evidence for a candidate person.",
                _UUID_PARAMETER,
                self._get_contact_evidence,
            ),
            "get_next_best_actions": ReadOnlyTool(
                "get_next_best_actions",
                "Return deterministic next actions, status, priorities and dependencies.",
                _PROJECT_PARAMETER,
                self._get_next_actions,
            ),
            "get_crm_readiness": ReadOnlyTool(
                "get_crm_readiness",
                "Return existing Pipedrive preview/readiness state; this tool cannot sync or write.",
                _PROJECT_PARAMETER,
                self._get_crm_readiness,
            ),
        }

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.definition() for tool in self._tools.values()]

    def call(self, name: str, arguments_json: str) -> Mapping[str, Any]:
        if name not in self._tools:
            raise KeyError(f"Tool {name!r} is not approved")
        arguments = json.loads(arguments_json or "{}")
        return self._tools[name].handler(arguments)

    @staticmethod
    def _uuid(value: str) -> UUID:
        return UUID(value)

    def _get_project(self, args: dict[str, Any]) -> Mapping[str, Any]:
        row = self.session.get(Project, self._uuid(args["project_id"]))
        if row is None:
            return {"found": False}
        return {
            "found": True,
            "project_id": str(row.id),
            "external_id": row.external_id,
            "canonical_name": row.canonical_name,
            "stage": row.stage,
            "category": row.category,
            "city": row.city,
            "region": row.region,
            "phase_label": row.phase_label,
            "state": row.state.value,
            "reported_value": str(row.reported_value) if row.reported_value is not None else None,
            "reported_value_is_source_fact_not_trusted_cost": True,
        }

    def _get_project_evidence(self, args: dict[str, Any]) -> Mapping[str, Any]:
        packet = self.evidence.project_packet(self._uuid(args["project_id"]))
        return {
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "excerpt": item.excerpt,
                    "page_number": item.page_number,
                    "classification": item.classification,
                }
                for item in packet
            ]
        }

    def _get_project_assessment(self, args: dict[str, Any]) -> Mapping[str, Any]:
        project_id = self._uuid(args["project_id"])
        row = self.session.scalar(
            sa.select(OpportunityAssessment)
            .where(OpportunityAssessment.project_id == project_id, OpportunityAssessment.is_current.is_(True))
            .order_by(OpportunityAssessment.computed_at.desc())
        )
        if row is None:
            return {"found": False}
        return {
            "found": True,
            "commercial_fit": float(row.commercial_fit_score),
            "data_confidence": float(row.data_confidence_score),
            "disposition": row.disposition,
            "confidence_state": row.confidence_state.value,
            "explanation": row.explanation,
        }

    def _get_product_fit(self, args: dict[str, Any]) -> Mapping[str, Any]:
        project_id = self._uuid(args["project_id"])
        assessment = self.session.scalar(
            sa.select(OpportunityAssessment)
            .where(OpportunityAssessment.project_id == project_id, OpportunityAssessment.is_current.is_(True))
            .order_by(OpportunityAssessment.computed_at.desc())
        )
        if assessment is None:
            return {"found": False, "products": []}
        rows = self.session.scalars(
            sa.select(ProductFitAssessment)
            .where(ProductFitAssessment.opportunity_assessment_id == assessment.id)
            .order_by(ProductFitAssessment.product_code)
        ).all()
        return {
            "found": True,
            "products": [
                {
                    "product_code": row.product_code,
                    "fit_score": float(row.fit_score),
                    "fit_band": row.fit_band,
                    "classification": row.classification.value,
                    "confidence_state": row.confidence_state.value,
                    "missing_evidence": row.missing_evidence,
                }
                for row in rows
            ],
        }

    def _get_account(self, args: dict[str, Any]) -> Mapping[str, Any]:
        row = self.session.get(Organization, self._uuid(args["id"]))
        if row is None:
            return {"found": False}
        return {
            "found": True,
            "organization_id": str(row.id),
            "canonical_name": row.canonical_name,
            "organization_type": row.organization_type,
            "status": row.status,
            "notes": row.notes,
        }

    def _get_contact_candidates(self, args: dict[str, Any]) -> Mapping[str, Any]:
        project_id = self._uuid(args["project_id"])
        candidates = self.session.scalars(
            sa.select(ContactCandidate)
            .where(ContactCandidate.project_id == project_id, ContactCandidate.is_current.is_(True))
            .order_by(ContactCandidate.rank.asc().nulls_last(), ContactCandidate.candidate_score.desc())
        ).all()
        result = []
        for candidate in candidates:
            person = self.session.get(Person, candidate.person_id)
            assessment = self.session.scalar(
                sa.select(ContactAssessment)
                .where(ContactAssessment.candidate_id == candidate.id, ContactAssessment.is_current.is_(True))
                .order_by(ContactAssessment.assessed_at.desc())
            )
            result.append(
                {
                    "candidate_id": str(candidate.id),
                    "person_id": str(candidate.person_id),
                    "display_name": person.display_name if person else "UNKNOWN",
                    "rank": candidate.rank,
                    "candidate_score": float(candidate.candidate_score or 0),
                    "target_persona": candidate.target_persona,
                    "state": candidate.state.value,
                    "employment": assessment.employment_state.value if assessment else "UNKNOWN",
                    "project_association": assessment.project_association_state.value if assessment else "UNKNOWN",
                    "role_relevance": assessment.role_relevance_state.value if assessment else "UNKNOWN",
                    "rental_authority": assessment.rental_authority_state.value if assessment else "UNKNOWN",
                    "rationale": candidate.rationale,
                }
            )
        return {"candidates": result}

    def _get_contact_evidence(self, args: dict[str, Any]) -> Mapping[str, Any]:
        person_id = self._uuid(args["id"])
        rows = self.session.scalars(
            sa.select(ExternalEvidence)
            .where(ExternalEvidence.person_id == person_id)
            .order_by(ExternalEvidence.retrieved_at.desc())
        ).all()
        return {
            "evidence": [
                {
                    "evidence_id": self.evidence.external_ref(row.id),
                    "publisher": row.publisher,
                    "source_title": row.source_title,
                    "claim": row.claim,
                    "classification": row.classification.value,
                    "verification_state": row.verification_state.value,
                    "retrieved_at": row.retrieved_at.isoformat(),
                }
                for row in rows
            ]
        }

    def _get_next_actions(self, args: dict[str, Any]) -> Mapping[str, Any]:
        project_id = self._uuid(args["project_id"])
        rows = self.session.scalars(
            sa.select(NextAction)
            .where(NextAction.project_id == project_id)
            .order_by(NextAction.priority.asc(), NextAction.created_at.asc())
        ).all()
        by_id = {row.id: row.action_type for row in rows}
        from app.commercial_workflow.service import CommercialWorkflowService

        kit = CommercialWorkflowService(self.session).current_first_call_kit(project_id)
        return {
            "actions": [
                {
                    "action_type": row.action_type,
                    "status": row.status.value,
                    "priority": row.priority,
                    "owner": row.owner,
                    "reason": row.reason,
                    "dependency": by_id.get(row.dependency_action_id),
                }
                for row in rows
            ],
            "first_call_kit": {
                "version": kit.version,
                "target_person_name": kit.target_person_name,
                "target_status": kit.target_status,
                "objective": kit.objective,
                "questions": list(kit.questions),
                "after_call_capture": list(kit.after_call_capture),
                "safeguards": list(kit.safeguards),
            },
        }

    def _get_crm_readiness(self, args: dict[str, Any]) -> Mapping[str, Any]:
        project_id = self._uuid(args["project_id"])
        records = self.session.scalars(
            sa.select(CRMRecord).where(CRMRecord.project_id == project_id).order_by(CRMRecord.object_type)
        ).all()
        sync_attempts = self.session.scalars(
            sa.select(CRMSyncAttempt)
            .join(CRMRecord, CRMSyncAttempt.crm_record_id == CRMRecord.id)
            .where(CRMRecord.project_id == project_id)
            .order_by(CRMSyncAttempt.attempted_at.desc())
        ).all()
        return {
            "records": [
                {
                    "object_type": row.object_type.value,
                    "promotion_state": row.promotion_state.value,
                    "sync_status": row.sync_status.value,
                    "canonical_key": row.canonical_key,
                }
                for row in records
            ],
            "latest_previews": [
                {
                    "status": row.status.value,
                    "mode": row.mode.value,
                    "request_payload": row.request_payload,
                    "error_detail": row.error_detail,
                }
                for row in sync_attempts[:4]
            ],
            "external_write_performed": False,
        }
