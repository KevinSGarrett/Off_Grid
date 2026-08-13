from __future__ import annotations

import re

from app.domain.states import ContactPointType, MaskingPolicy


class DemoPrivacyError(ValueError):
    """Raised when a value cannot be safely rendered under the requested demo policy."""


def mask_email(value: str) -> str:
    local, sep, domain = value.partition("@")
    if not sep or not local or not domain:
        return "***"
    visible = local[:1]
    return f"{visible}***@{domain}"


def mask_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 4:
        return "***"
    return f"***-***-{digits[-4:]}"


def mask_generic(value: str) -> str:
    if not value:
        return "***"
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * min(8, len(value) - 2) + value[-1]


def render_demo_value(
    value: str | None,
    *,
    policy: MaskingPolicy,
    contact_type: ContactPointType | None = None,
    demo_mode: bool = True,
) -> str | None:
    """Return a demo-safe display value.

    In non-demo/private operation, the original value is returned. In demo mode HIDDEN/FULL
    never exposes source text; PARTIAL uses type-aware masking. The raw value remains in the
    private persistence model and is never required in employer-facing response schemas.
    """
    if value is None:
        return None
    if not demo_mode or policy == MaskingPolicy.NONE:
        return value
    if policy == MaskingPolicy.HIDDEN:
        return None
    if policy == MaskingPolicy.FULL:
        return "***"
    if policy != MaskingPolicy.PARTIAL:
        raise DemoPrivacyError(f"Unsupported masking policy: {policy}")
    if contact_type == ContactPointType.EMAIL:
        return mask_email(value)
    if contact_type in {ContactPointType.PHONE, ContactPointType.FAX}:
        return mask_phone(value)
    return mask_generic(value)


def sanitize_audit_metadata(metadata: dict | None) -> dict | None:
    """Remove common raw-contact/secret fields before an event is persisted.

    This is a conservative persistence guardrail. Integration code should pass references/hashes
    rather than raw payloads wherever possible.
    """
    if metadata is None:
        return None
    forbidden_fragments = (
        "email",
        "phone",
        "fax",
        "token",
        "secret",
        "password",
        "api_key",
        "apikey",
        "authorization",
    )
    clean: dict = {}
    for key, value in metadata.items():
        normalized = key.lower()
        if any(fragment in normalized for fragment in forbidden_fragments):
            clean[key] = "[REDACTED]"
        else:
            clean[key] = value
    return clean
