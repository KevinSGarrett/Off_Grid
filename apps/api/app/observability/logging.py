from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.observability.context import current_context

OBSERVABILITY_VERSION = "observability-1.0"
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|token|cookie|credential)", re.IGNORECASE
)
_EMAIL = re.compile(r"\b([A-Z0-9._%+-]{1,64})@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)
# Deliberately conservative: mask long telephone-looking strings without rewriting timestamps/IDs.
_PHONE = re.compile(r"(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\w)")
_PRIVATE_PATH = re.compile(r"(?:/mnt/data|data/private|private://)[^\s\"']*", re.IGNORECASE)


def _mask_email(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        local, domain = match.group(1), match.group(2)
        return f"{local[:1]}***@{domain}"

    return _EMAIL.sub(repl, value)


def sanitize_for_log(value: Any, *, key: str | None = None) -> Any:
    """Return a log-safe JSON-compatible value.

    Logs must never become an alternate copy of the EE Reed contact directory or secret store. The
    sanitizer therefore redacts credential-shaped keys and masks common business-contact/path data.
    It is intentionally defensive even though Wave 14 request logging never records request bodies.
    """

    if key and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): sanitize_for_log(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_for_log(item) for item in value]
    if isinstance(value, str):
        text = _PRIVATE_PATH.sub("[PRIVATE_PATH]", value)
        text = _mask_email(text)
        text = _PHONE.sub("[MASKED_PHONE]", text)
        return text[:4000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:4000]


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        context = current_context()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": sanitize_for_log(record.getMessage()),
            "request_id": context["request_id"],
            "pipeline_run_id": context["pipeline_run_id"],
            "observability_version": OBSERVABILITY_VERSION,
        }
        safe_extra = getattr(record, "safe_extra", None)
        if safe_extra:
            payload["fields"] = sanitize_for_log(safe_extra)
        if record.exc_info:
            # Exception *types* are useful; raw tracebacks may contain filesystem/source values.
            payload["exception_type"] = (
                record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            )
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def configure_structured_logging(
    *, level: str = "INFO", stream: Any | None = None
) -> logging.Logger:
    logger = logging.getLogger("offgrid")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    # Idempotent setup: application factories/tests may be constructed repeatedly.
    for handler in list(logger.handlers):
        if getattr(handler, "_offgrid_structured", False):
            logger.removeHandler(handler)
    stream_handler: Any = logging.StreamHandler(stream)
    stream_handler._offgrid_structured = True
    stream_handler.setFormatter(JsonLogFormatter())
    logger.addHandler(stream_handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"offgrid.{name}")
