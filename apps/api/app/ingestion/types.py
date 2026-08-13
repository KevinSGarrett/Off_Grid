from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

ReportType = Literal["PROJECT", "COMPANY"]
CompanySection = Literal["PLANNING", "POST_BID", "BIDDING_ROLE"]


@dataclass(frozen=True)
class EvidenceRef:
    page: int
    section: str
    excerpt: str


@dataclass(frozen=True)
class DesignTeamRow:
    role: str
    company_name: str
    contact_name: str | None = None
    contact_status: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    fax: str | None = None
    page: int = 1


@dataclass(frozen=True)
class ParsedProjectReport:
    report_type: Literal["PROJECT"]
    source_path: Path
    project_name: str
    project_id: str
    category: str | None
    street_address: str | None
    city: str | None
    region: str | None
    postal_code: str | None
    county: str | None
    estimated_value_raw: str | None
    estimated_value: Decimal | None
    stage: str | None
    last_update: date | None
    scope: str | None
    description: str | None
    notes: str | None
    listed_on: date | None
    floor_area_raw: str | None
    floor_area_sqft: int | None
    work_type: str | None
    owner_type: str | None
    start_date: date | None
    start_date_label: str | None
    structures: int | None
    report_date: datetime
    design_team: tuple[DesignTeamRow, ...]
    currently_tracked: bool | None
    viewed_by: str | None
    evidence: dict[str, EvidenceRef] = field(default_factory=dict)


@dataclass(frozen=True)
class CompanyProjectRow:
    section: CompanySection
    row_number: int
    project_name: str
    contact: str | None
    role: str | None
    city: str | None
    region: str | None
    value_raw: str | None
    value: Decimal | None
    stage: str | None
    bid_date_raw: str | None = None
    bid_date: date | None = None
    bid_amount_raw: str | None = None
    bid_amount: Decimal | None = None
    bid_rank_raw: str | None = None
    bid_rank: int | None = None
    page: int = 1
    raw_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompanyContactRow:
    row_number: int
    name: str
    phone: str | None
    fax: str | None
    email: str | None
    address: str | None
    status: str | None
    page: int = 6
    raw_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationResult:
    expected_planning: int
    parsed_planning: int
    expected_post_bid: int
    parsed_post_bid: int
    expected_bidding_role: int
    parsed_bidding_role: int

    @property
    def passed(self) -> bool:
        return (
            self.expected_planning == self.parsed_planning
            and self.expected_post_bid == self.parsed_post_bid
            and self.expected_bidding_role == self.parsed_bidding_role
        )


@dataclass(frozen=True)
class ParsedCompanyReport:
    report_type: Literal["COMPANY"]
    source_path: Path
    company_name: str
    company_id: str
    classification: str | None
    street_address: str | None
    company_fax: str | None
    bidding_projects: int
    company_email: str | None
    planning_projects: int
    post_bid_projects: int
    company_website: str | None
    bidding_role_projects: int
    company_phone: str | None
    last_update: datetime | None
    report_date: datetime
    planning_rows: tuple[CompanyProjectRow, ...]
    post_bid_rows: tuple[CompanyProjectRow, ...]
    bidding_role_rows: tuple[CompanyProjectRow, ...]
    contacts: tuple[CompanyContactRow, ...]
    reconciliation: ReconciliationResult
    currently_tracked: bool | None
    viewed_by: str | None
    evidence: dict[str, EvidenceRef] = field(default_factory=dict)
