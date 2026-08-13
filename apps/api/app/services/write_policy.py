from __future__ import annotations

from dataclasses import dataclass

from app.domain.errors import ExternalWriteBlocked
from app.domain.states import IntegrationMode


@dataclass(frozen=True, slots=True)
class ExternalWriteContext:
    demo_mode: bool
    integration_mode: IntegrationMode
    credentials_present: bool
    readiness_passed: bool
    authorized: bool = True


class ExternalWriteGate:
    """Fail-closed server-side policy for any third-party mutation."""

    @staticmethod
    def assert_live_write_allowed(ctx: ExternalWriteContext) -> None:
        reasons: list[str] = []
        if ctx.demo_mode:
            reasons.append("DEMO_MODE blocks external writes")
        if ctx.integration_mode is not IntegrationMode.LIVE:
            reasons.append(f"integration mode is {ctx.integration_mode.value!r}, not 'live'")
        if not ctx.credentials_present:
            reasons.append("credentials are not configured")
        if not ctx.readiness_passed:
            reasons.append("domain readiness gate did not pass")
        if not ctx.authorized:
            reasons.append("runtime/user context is not authorized")
        if reasons:
            raise ExternalWriteBlocked("; ".join(reasons))
