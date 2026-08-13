import pytest

from app.domain.errors import ExternalWriteBlocked
from app.domain.states import IntegrationMode
from app.services.write_policy import ExternalWriteContext, ExternalWriteGate


def test_demo_mode_blocks_even_live_configured_write() -> None:
    ctx = ExternalWriteContext(
        demo_mode=True,
        integration_mode=IntegrationMode.LIVE,
        credentials_present=True,
        readiness_passed=True,
    )
    with pytest.raises(ExternalWriteBlocked, match="DEMO_MODE"):
        ExternalWriteGate.assert_live_write_allowed(ctx)


def test_dry_run_mode_blocks_write() -> None:
    ctx = ExternalWriteContext(
        demo_mode=False,
        integration_mode=IntegrationMode.DRY_RUN,
        credentials_present=True,
        readiness_passed=True,
    )
    with pytest.raises(ExternalWriteBlocked, match="not 'live'"):
        ExternalWriteGate.assert_live_write_allowed(ctx)


def test_live_write_requires_all_server_side_gates() -> None:
    ctx = ExternalWriteContext(
        demo_mode=False,
        integration_mode=IntegrationMode.LIVE,
        credentials_present=True,
        readiness_passed=True,
        authorized=True,
    )
    ExternalWriteGate.assert_live_write_allowed(ctx)
