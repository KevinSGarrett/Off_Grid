from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FactorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    max_points: Decimal
    adjusted_points: Decimal
    matched_rule_keys: tuple[str, ...]
    explanation: str


class ProductFitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_code: str
    product_name: str
    fit_score: Decimal
    fit_band: str
    classification: str
    missing_evidence: tuple[str, ...]
    explanation: str


class DecisionUnknownRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    impact_score: int
    impact_band: str
    validation: str


class QualificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    project_id: UUID
    external_project_id: str | None
    model_version: str
    commercial_fit_score: Decimal
    data_confidence_score: Decimal
    disposition: str
    operational_action: str
    confidence_state: str
    factors: tuple[FactorRead, ...]
    product_fits: tuple[ProductFitRead, ...]
    decision_changing_unknowns: tuple[DecisionUnknownRead, ...]
