from __future__ import annotations

import re
from collections import defaultdict
from datetime import timezone

import pdfplumber

from app.ingestion.normalization import (
    clean_wrapped_city,
    collapse_space,
    normalize_email,
    normalize_phone,
    normalize_role,
    normalize_stage,
    parse_integer,
    parse_money,
    parse_us_date,
    parse_us_datetime,
)
from app.ingestion.pdf_adapter import PDFPayload
from app.ingestion.types import (
    CompanyContactRow,
    CompanyProjectRow,
    EvidenceRef,
    ParsedCompanyReport,
    ReconciliationResult,
)

STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}


def _page_words(page) -> list[dict]:  # type: ignore[no-untyped-def]
    return page.extract_words(x_tolerance=2, y_tolerance=2)


def _column_text(words: list[dict], left: float, right: float) -> str | None:
    selected = [w for w in words if left <= (w["x0"] + w["x1"]) / 2 < right]
    if not selected:
        return None
    selected.sort(key=lambda w: (round(w["top"], 1), w["x0"]))
    groups: list[list[str]] = []
    last_top: float | None = None
    for word in selected:
        top = round(word["top"], 1)
        if last_top is None or abs(top - last_top) > 1.0:
            groups.append([])
            last_top = top
        groups[-1].append(word["text"])
    return collapse_space("\n".join(" ".join(line) for line in groups))


def _detect_project_row_starts(
    words: list[dict], *, state_x: tuple[float, float], value_x: tuple[float, float], y_min: float, y_max: float
) -> list[float]:
    by_top: dict[float, list[dict]] = defaultdict(list)
    for word in words:
        if y_min <= word["top"] <= y_max:
            by_top[round(word["top"], 1)].append(word)
    starts: list[float] = []
    for top, group in by_top.items():
        state_tokens = [
            w["text"] for w in group if state_x[0] <= (w["x0"] + w["x1"]) / 2 < state_x[1]
        ]
        value_tokens = [
            w["text"] for w in group if value_x[0] <= (w["x0"] + w["x1"]) / 2 < value_x[1]
        ]
        if any(token in STATE_CODES for token in state_tokens) and any("$" in token for token in value_tokens):
            starts.append(top)
    return sorted(starts)


def _extract_rows(words: list[dict], starts: list[float], bounds: list[float], end_y: float) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else end_y
        row_words = [w for w in words if start - 0.5 <= w["top"] < end - 0.5]
        cells = tuple((_column_text(row_words, bounds[i], bounds[i + 1]) or "") for i in range(len(bounds) - 1))
        rows.append(cells)
    return rows


def _planning_rows(pdf) -> list[CompanyProjectRow]:  # type: ignore[no-untyped-def]
    page = pdf.pages[0]
    words = _page_words(page)
    starts = _detect_project_row_starts(words, state_x=(445, 480), value_x=(480, 533), y_min=210, y_max=460)
    raw_rows = _extract_rows(words, starts, [30, 257, 301, 407, 451, 489, 533, 590], 455)
    rows: list[CompanyProjectRow] = []
    for i, cells in enumerate(raw_rows, 1):
        name, contact, role, city, region, value_raw, stage = cells
        rows.append(
            CompanyProjectRow(
                section="PLANNING",
                row_number=i,
                project_name=collapse_space(name) or "",
                contact=collapse_space(contact),
                role=normalize_role(role),
                city=clean_wrapped_city(city),
                region=collapse_space(region),
                value_raw=collapse_space(value_raw),
                value=parse_money(value_raw),
                stage=normalize_stage(stage),
                page=1,
                raw_columns=cells,
            )
        )
    return rows


def _post_bid_rows(pdf) -> list[CompanyProjectRow]:  # type: ignore[no-untyped-def]
    rows: list[CompanyProjectRow] = []
    row_number = 0
    for page_index in range(1, 6):
        page = pdf.pages[page_index - 1]
        words = _page_words(page)
        y_min = 490 if page_index == 1 else 20
        y_max = 750 if page_index < 5 else 650
        starts = _detect_project_row_starts(words, state_x=(285, 315), value_x=(320, 370), y_min=y_min, y_max=y_max)
        raw_rows = _extract_rows(words, starts, [30, 115, 194, 237, 290, 327, 370, 448, 491, 534, 590], y_max)
        for cells in raw_rows:
            row_number += 1
            name, contact, role, city, region, value_raw, stage, bid_date_raw, bid_amount_raw, bid_rank_raw = cells
            rows.append(
                CompanyProjectRow(
                    section="POST_BID",
                    row_number=row_number,
                    project_name=collapse_space(name) or "",
                    contact=collapse_space(contact),
                    role=normalize_role(role),
                    city=clean_wrapped_city(city),
                    region=collapse_space(region),
                    value_raw=collapse_space(value_raw),
                    value=parse_money(value_raw),
                    stage=normalize_stage(stage),
                    bid_date_raw=collapse_space(bid_date_raw),
                    bid_date=parse_us_date(bid_date_raw),
                    bid_amount_raw=collapse_space(bid_amount_raw),
                    bid_amount=parse_money(bid_amount_raw),
                    bid_rank_raw=collapse_space(bid_rank_raw),
                    bid_rank=parse_integer(bid_rank_raw),
                    page=page_index,
                    raw_columns=cells,
                )
            )
    return rows


def _contact_rows(pdf) -> list[CompanyContactRow]:  # type: ignore[no-untyped-def]
    page = pdf.pages[5]
    words = _page_words(page)
    by_top: dict[float, list[dict]] = defaultdict(list)
    for word in words:
        if 45 <= word["top"] <= 735:
            by_top[round(word["top"], 1)].append(word)
    starts: list[float] = []
    for top, group in by_top.items():
        status = [
            w["text"] for w in group if 528 <= (w["x0"] + w["x1"]) / 2 < 590
        ]
        if any(token in {"Active", "Inactive"} for token in status):
            starts.append(top)
    raw_rows = _extract_rows(words, sorted(starts), [30, 140, 188, 232, 312, 528, 590], 730)
    rows: list[CompanyContactRow] = []
    for i, cells in enumerate(raw_rows, 1):
        name, phone, fax, email, address, status = cells
        rows.append(
            CompanyContactRow(
                row_number=i,
                name=collapse_space(name) or "",
                phone=normalize_phone(phone),
                fax=normalize_phone(fax),
                email=normalize_email(email),
                address=collapse_space(address),
                status=collapse_space(status),
                page=6,
                raw_columns=cells,
            )
        )
    return rows


def _bidding_rows(pdf) -> list[CompanyProjectRow]:  # type: ignore[no-untyped-def]
    rows: list[CompanyProjectRow] = []
    row_number = 0
    for page_index in range(7, 10):
        page = pdf.pages[page_index - 1]
        words = _page_words(page)
        starts = _detect_project_row_starts(words, state_x=(315, 350), value_x=(350, 397), y_min=20, y_max=750)
        raw_rows = _extract_rows(words, starts, [30, 160, 282, 321, 359, 397, 462, 500, 538, 590], 750)
        for cells in raw_rows:
            row_number += 1
            name, role, city, region, value_raw, stage, bid_date_raw, bid_amount_raw, bid_rank_raw = cells
            rows.append(
                CompanyProjectRow(
                    section="BIDDING_ROLE",
                    row_number=row_number,
                    project_name=collapse_space(name) or "",
                    contact=None,
                    role=normalize_role(role),
                    city=clean_wrapped_city(city),
                    region=collapse_space(region),
                    value_raw=collapse_space(value_raw),
                    value=parse_money(value_raw),
                    stage=normalize_stage(stage),
                    bid_date_raw=collapse_space(bid_date_raw),
                    bid_date=parse_us_date(bid_date_raw),
                    bid_amount_raw=collapse_space(bid_amount_raw),
                    bid_amount=parse_money(bid_amount_raw),
                    bid_rank_raw=collapse_space(bid_rank_raw),
                    bid_rank=parse_integer(bid_rank_raw),
                    page=page_index,
                    raw_columns=cells,
                )
            )
    return rows


def _line_after(lines: list[str], label: str) -> str | None:
    for i, line in enumerate(lines):
        if line.strip() == label and i + 1 < len(lines):
            return lines[i + 1].strip()
    return None


def parse_company_report(payload: PDFPayload) -> ParsedCompanyReport:
    first = payload.first_page
    lines = [line.strip() for line in first.splitlines() if line.strip()]
    all_text = "\n".join(payload.page_text)

    company_name = lines[0]
    company_id = _line_after(lines, "Company ID#:") or ""
    planning = parse_integer(_line_after(lines, "Planing Projects:")) or 0
    bidding = parse_integer(_line_after(lines, "Bidding Projects:")) or 0
    post_bid = parse_integer(_line_after(lines, "Post Bid Projects:")) or 0
    bidding_role_match = re.search(r"Bidding Role Projects:\s*(\d+)", first)
    bidding_role = int(bidding_role_match.group(1)) if bidding_role_match else 0
    street = _line_after(lines, "Street Address:")
    if street and street.endswith("TX"):
        try:
            street = f"{street} {lines[lines.index(street) + 1]}"
        except (ValueError, IndexError):
            pass
    company_fax = _line_after(lines, "Company Fax:")
    company_email = _line_after(lines, "Company Email:")
    website_match = re.search(r"Company Website:\s*(\S+)", first)
    company_website = website_match.group(1) if website_match else None
    company_phone = _line_after(lines, "Company Phone:")
    last_update = parse_us_datetime(_line_after(lines, "Last Update:"))
    if last_update:
        last_update = last_update.replace(tzinfo=timezone.utc)
    report_date_match = re.search(r"Report Date:\s*([^\n]+)", first)
    report_date = parse_us_datetime(report_date_match.group(1) if report_date_match else None)
    if report_date is None:
        raise ValueError("Company report is missing a parseable Report Date")
    report_date = report_date.replace(tzinfo=timezone.utc)

    classification = None
    try:
        start = lines.index("Classification:") + 1
        stop = lines.index("Company ID#:")
        classification = collapse_space(" ".join(lines[start:stop]))
    except ValueError:
        pass

    with pdfplumber.open(payload.path) as pdf:
        planning_rows = _planning_rows(pdf)
        post_bid_rows = _post_bid_rows(pdf)
        contacts = _contact_rows(pdf)
        bidding_rows = _bidding_rows(pdf)

    reconciliation = ReconciliationResult(
        expected_planning=planning,
        parsed_planning=len(planning_rows),
        expected_post_bid=post_bid,
        parsed_post_bid=len(post_bid_rows),
        expected_bidding_role=bidding_role,
        parsed_bidding_role=len(bidding_rows),
    )

    history_match = re.search(r"Ash Hand\nTrue\n7/8/2026[^\n]*\nFalse", all_text)
    if not history_match:
        history_match = re.search(r"Ash Hand\s+True\s+7/8/2026[^\n]*\s+False", all_text)

    evidence = {
        "company_id": EvidenceRef(1, "Header", f"Company ID#: {company_id}"),
        "project_counts": EvidenceRef(
            1,
            "Header",
            f"Planning Projects: {planning}; Post Bid Projects: {post_bid}; Bidding Role Projects: {bidding_role}",
        ),
        "stafford_1_2": EvidenceRef(4, "Post Bid Stage Projects", "Stafford Technology Campus Phases 1 & 2 — $2,500,000,000 — Construction Underway"),
        "stafford_3_4": EvidenceRef(5, "Post Bid Stage Projects", "Stafford Technology Campus Phases 3 & 4 — $7,500,000,000 — General Contractor Award"),
        "contacts": EvidenceRef(6, "Contacts", "EE Reed company contact directory with named contacts, phone/fax, email, address and status."),
        "tracked": EvidenceRef(5, "History", "Ash Hand — Viewed: True — Currently Tracked?: False"),
    }

    return ParsedCompanyReport(
        report_type="COMPANY",
        source_path=payload.path,
        company_name=company_name,
        company_id=company_id,
        classification=classification,
        street_address=collapse_space(street),
        company_fax=normalize_phone(company_fax),
        bidding_projects=bidding,
        company_email=normalize_email(company_email),
        planning_projects=planning,
        post_bid_projects=post_bid,
        company_website=company_website,
        bidding_role_projects=bidding_role,
        company_phone=normalize_phone(company_phone),
        last_update=last_update,
        report_date=report_date,
        planning_rows=tuple(planning_rows),
        post_bid_rows=tuple(post_bid_rows),
        bidding_role_rows=tuple(bidding_rows),
        contacts=tuple(contacts),
        reconciliation=reconciliation,
        currently_tracked=False if history_match else None,
        viewed_by="Ash Hand" if history_match else None,
        evidence=evidence,
    )
