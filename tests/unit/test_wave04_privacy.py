from __future__ import annotations

from app.domain.states import ContactPointType, MaskingPolicy
from app.schemas.entities import DemoContactPointRead
from app.services.privacy import mask_email, mask_phone, render_demo_value, sanitize_audit_metadata


def test_partial_email_mask_preserves_domain_but_not_local_identity() -> None:
    assert mask_email("jane@example.com") == "j***@example.com"


def test_partial_phone_mask_shows_only_last_four_digits() -> None:
    assert mask_phone("(281) 555-1234") == "***-***-1234"


def test_demo_masking_policies_are_fail_safe() -> None:
    assert render_demo_value("jane@example.com", policy=MaskingPolicy.HIDDEN, demo_mode=True) is None
    assert render_demo_value("jane@example.com", policy=MaskingPolicy.FULL, demo_mode=True) == "***"
    assert (
        render_demo_value(
            "jane@example.com",
            policy=MaskingPolicy.PARTIAL,
            contact_type=ContactPointType.EMAIL,
            demo_mode=True,
        )
        == "j***@example.com"
    )
    assert render_demo_value("jane@example.com", policy=MaskingPolicy.NONE, demo_mode=True) == "jane@example.com"
    assert render_demo_value("jane@example.com", policy=MaskingPolicy.PARTIAL, demo_mode=False) == "jane@example.com"


def test_demo_schema_has_no_raw_contact_value_field() -> None:
    assert "value" not in DemoContactPointRead.model_fields
    assert "normalized_value" not in DemoContactPointRead.model_fields
    assert "display_value" in DemoContactPointRead.model_fields


def test_audit_metadata_redacts_contact_and_secret_like_fields() -> None:
    result = sanitize_audit_metadata(
        {
            "contact_email": "person@example.com",
            "phone_number": "2815551212",
            "api_key": "secret-key",
            "project_id": "1007341663",
        }
    )
    assert result == {
        "contact_email": "[REDACTED]",
        "phone_number": "[REDACTED]",
        "api_key": "[REDACTED]",
        "project_id": "1007341663",
    }
