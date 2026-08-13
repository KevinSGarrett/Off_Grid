from __future__ import annotations

import re
from datetime import timezone
from pathlib import Path

import pdfplumber

from app.ingestion.normalization import (
    collapse_space,
    normalize_email,
    normalize_phone,
    parse_integer,
    parse_money,
    parse_us_date,
    parse_us_datetime,
)
from app.ingestion.pdf_adapter import PDFPayload
from app.ingestion.types import DesignTeamRow, EvidenceRef, ParsedProjectReport

_ROLE_NAMES = {"Architect", "General Contractor", "Owner", "Developer", "Consultant", "Civil Engineer"}
_COLUMNS = [30, 118, 198, 263, 306, 387, 441, 522, 590]


def _capture(text: str, pattern: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _line_after(lines: list[str], label: str, occurrence: int = 1) -> str | None:
    seen = 0
    for i, line in enumerate(lines):
        if line.strip() == label:
            seen += 1
            if seen == occurrence and i + 1 < len(lines):
                return lines[i + 1].strip()
    return None


def _join_column(words: list[dict], left: float, right: float) -> str | None:
    selected = [w for w in words if left <= (w["x0"] + w["x1"]) / 2 < right]
    if not selected:
        return None
    selected.sort(key=lambda w: (round(w["top"], 1), w["x0"]))
    lines: list[list[str]] = []
    last_top: float | None = None
    for word in selected:
        top = round(word["top"], 1)
        if last_top is None or abs(top - last_top) > 1.0:
            lines.append([])
            last_top = top
        lines[-1].append(word["text"])
    return collapse_space("\n".join(" ".join(line) for line in lines))


def _design_team_rows(path: Path) -> tuple[DesignTeamRow, ...]:
    rows: list[DesignTeamRow] = []
    with pdfplumber.open(path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            groups: dict[float, list[dict]] = {}
            for word in words:
                groups.setdefault(round(word["top"], 1), []).append(word)
            starts: list[tuple[float, str]] = []
            for top, group in groups.items():
                role_words = sorted(
                    [w for w in group if 30 <= (w["x0"] + w["x1"]) / 2 < 118],
                    key=lambda w: w["x0"],
                )
                role_text = " ".join(w["text"] for w in role_words)
                if role_text in _ROLE_NAMES:
                    starts.append((top, role_text))
            starts.sort()
            stop_candidates = [
                w["top"] for w in words
                if (w["text"] == "HHiissttoorryy") or (w["text"] == "Report" and w["x0"] < 40)
            ]
            section_end = min(stop_candidates) - 2 if stop_candidates else page.height
            for idx, (start, role) in enumerate(starts):
                end = starts[idx + 1][0] if idx + 1 < len(starts) else section_end
                row_words = [w for w in words if start - 0.5 <= w["top"] < end - 0.5]
                cells = [_join_column(row_words, _COLUMNS[i], _COLUMNS[i + 1]) for i in range(8)]
                company = cells[1]
                if not company:
                    continue
                rows.append(
                    DesignTeamRow(
                        role=role,
                        company_name=company,
                        contact_name=re.sub(r"([A-Za-z]{4,}) ([A-Za-z])$", r"\1\2", cells[2]) if cells[2] else None,
                        contact_status=cells[3],
                        address=cells[4],
                        phone=normalize_phone(cells[5]),
                        email=normalize_email(cells[6]),
                        fax=normalize_phone(cells[7]),
                        page=page_index,
                    )
                )
    return tuple(rows)


def parse_project_report(payload: PDFPayload) -> ParsedProjectReport:
    text = payload.first_page
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    all_text = "\n".join(payload.page_text)

    project_name = lines[0]
    project_id = _line_after(lines, "Project ID #:") or ""
    category = _line_after(lines, "Category:")
    street_line = _line_after(lines, "Street Address:")
    location_line = None
    if street_line:
        try:
            idx = lines.index(street_line)
            location_line = lines[idx + 1]
        except (ValueError, IndexError):
            location_line = None
    city = region = postal = None
    if location_line:
        m = re.match(r"(.+?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$", location_line)
        if m:
            city, region, postal = m.groups()

    value_raw = _line_after(lines, "Staff Estimate Value")
    county = _line_after(lines, "County:")
    stage = _line_after(lines, "Stage:")
    last_update = parse_us_date(_line_after(lines, "Last Update:"))
    report_date_raw = _capture(all_text, r"Report Date:\s*([^\n]+)")
    report_date = parse_us_datetime(report_date_raw)
    if report_date is None:
        raise ValueError("Project report is missing a parseable Report Date")
    report_date = report_date.replace(tzinfo=timezone.utc)

    scope = _capture(text, r"Scope\n(.+?)\nCompleted plans", re.S)
    description = _capture(text, r"(Completed plans.+?)\nNotes\n", re.S)
    notes = _capture(text, r"Notes\n(.+?)\nProject Events", re.S)
    listed_on = parse_us_date(_line_after(lines, "Listed On:"))
    floor_area_raw = _line_after(lines, "Floor Area:")
    floor_area = parse_integer(floor_area_raw)
    work_type = _line_after(lines, "Work Type:")
    owner_type = _line_after(lines, "Owner Type:")
    start_date = parse_us_date(_line_after(lines, "Start Date"))
    start_label = None
    if "Project Events" in lines:
        try:
            event_idx = lines.index("Start Date", lines.index("Project Events"))
            start_label = lines[event_idx + 2] if event_idx + 2 < len(lines) else None
        except (ValueError, IndexError):
            pass
    structures = parse_integer(_line_after(lines, "Structures:"))

    tracked_match = re.search(r"Ash Hand\nTrue\n7/8/2026\nFalse", all_text)
    currently_tracked = False if tracked_match else None
    viewed_by = "Ash Hand" if tracked_match else None

    caveat = (
        "The listed square footage and value are estimated based on total project projections. "
        "A confirmed scope, total number of phases, and construction costs for each have not been publicly released."
    )
    evidence = {
        "project_id": EvidenceRef(1, "Header", f"Project ID #: {project_id}"),
        "reported_value": EvidenceRef(1, "Header", f"Staff Estimate Value {value_raw}"),
        "stage": EvidenceRef(1, "Header", f"Stage: {stage}"),
        "scope": EvidenceRef(1, "Project Description", collapse_space(scope) or ""),
        "description": EvidenceRef(1, "Project Description", collapse_space(description) or ""),
        "notes": EvidenceRef(1, "Project Description", collapse_space(notes) or ""),
        "floor_area": EvidenceRef(1, "Additional Details", f"Floor Area: {floor_area_raw}"),
        "work_type": EvidenceRef(1, "Additional Details", f"Work Type: {work_type}"),
        "value_caveat": EvidenceRef(1, "Project Description", caveat),
        "start_date": EvidenceRef(1, "Project Events", f"Start Date {start_date} {start_label}"),
        "tracked": EvidenceRef(2, "History", "Ash Hand — Viewed: True — Currently Tracked?: False"),
    }

    return ParsedProjectReport(
        report_type="PROJECT",
        source_path=payload.path,
        project_name=project_name,
        project_id=project_id,
        category=category,
        street_address=street_line,
        city=city,
        region=region,
        postal_code=postal,
        county=county,
        estimated_value_raw=value_raw,
        estimated_value=parse_money(value_raw),
        stage=stage,
        last_update=last_update,
        scope=collapse_space(scope),
        description=collapse_space(description),
        notes=collapse_space(notes),
        listed_on=listed_on,
        floor_area_raw=floor_area_raw,
        floor_area_sqft=floor_area,
        work_type=work_type,
        owner_type=owner_type,
        start_date=start_date,
        start_date_label=start_label,
        structures=structures,
        report_date=report_date,
        design_team=_design_team_rows(payload.path),
        currently_tracked=currently_tracked,
        viewed_by=viewed_by,
        evidence=evidence,
    )
