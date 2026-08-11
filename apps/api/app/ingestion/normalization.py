from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_SPACE_RE = re.compile(r"\s+")
_NON_MONEY_RE = re.compile(r"[^0-9.\-]")
_GENERIC_EMAIL_LOCALS = {"info", "contact", "office", "admin", "sales", "hello", "support"}


def collapse_space(value: str | None) -> str | None:
    if value is None:
        return None
    text = _SPACE_RE.sub(" ", value.replace("\x00", " ")).strip()
    return text or None


def normalized_name(value: str) -> str:
    text = collapse_space(value) or ""
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return collapse_space(text) or ""


def canonical_slug(value: str) -> str:
    return normalized_name(value).replace(" ", "-")


def parse_money(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = _NON_MONEY_RE.sub("", value)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_integer(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9\-]", "", value)
    if not digits or digits == "-":
        return None
    return int(digits)


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", "", value).strip(".,;:").lower()
    return text or None


def email_domain(value: str | None) -> str | None:
    email = normalize_email(value)
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1]


def is_generic_email(value: str | None) -> bool:
    email = normalize_email(value)
    if not email or "@" not in email:
        return False
    return email.split("@", 1)[0] in _GENERIC_EMAIL_LOCALS


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"+1{digits}"
    return digits or None


def parse_us_date(value: str | None) -> date | None:
    if not value:
        return None
    compact = re.sub(r"\s+", "", value)
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(compact, fmt).date()
        except ValueError:
            continue
    return None


def parse_us_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    compact = collapse_space(value)
    if not compact:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(compact, fmt)
        except ValueError:
            continue
    return None


def normalize_stage(value: str | None) -> str | None:
    text = collapse_space(value)
    if not text:
        return None
    # Repair line-wrap artifacts common in the supplied report without changing semantics.
    replacements = {
        "Construct ion": "Construction",
        "General Contract or": "General Contractor",
        "General Contractor Award": "General Contractor Award",
        "Pre- Design": "Pre-Design",
        "Construction Documen ts": "Construction Documents",
        "Construct ion Documen ts": "Construction Documents",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def normalize_role(value: str | None) -> str | None:
    text = collapse_space(value)
    if not text:
        return None
    return (
        text.replace("General Contract or", "General Contractor")
        .replace("Construct ion Manager", "Construction Manager")
    )


def clean_wrapped_city(value: str | None) -> str | None:
    text = collapse_space(value)
    if not text:
        return None
    # These are line-wrap artifacts in the validated Company report format, not semantic aliases.
    repaired = {
        "Fredericksb urg": "Fredericksburg",
        "Hardeev ille": "Hardeeville",
        "Swainsb oro": "Swainsboro",
        "Pasade na": "Pasadena",
        "Savann ah": "Savannah",
        "Richmo nd": "Richmond",
        "Ridgevill e": "Ridgeville",
        "Corpus Christi": "Corpus Christi",
        "Rosenbe rg": "Rosenberg",
        "Sugar Land": "Sugar Land",
        "Pearlan d": "Pearland",
        "Summer ville": "Summerville",
        "Hanaha n": "Hanahan",
        "Magnoli a": "Magnolia",
        "Brookshi re": "Brookshire",
        "Missouri City": "Missouri City",
        "The Woodlands": "The Woodlands",
        "San Marcos": "San Marcos",
        "College Station": "College Station",
        "Port Arthur": "Port Arthur",
    }
    return repaired.get(text, text)
