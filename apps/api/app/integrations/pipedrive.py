from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.domain.states import IntegrationMode
from app.services.write_policy import ExternalWriteContext, ExternalWriteGate


class PipedriveTransport(Protocol):
    def request(self, method: str, path: str, *, json: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class PipedriveAdapter:
    mode: IntegrationMode
    demo_mode: bool
    credentials_present: bool = False
    transport: PipedriveTransport | None = None

    def preview(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"mode": self.mode.value, "preview": dict(payload), "external_write": False}

    def execute(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any],
        *,
        readiness_passed: bool,
        authorized: bool = True,
    ) -> Mapping[str, Any]:
        ExternalWriteGate.assert_live_write_allowed(
            ExternalWriteContext(
                demo_mode=self.demo_mode,
                integration_mode=self.mode,
                credentials_present=self.credentials_present,
                readiness_passed=readiness_passed,
                authorized=authorized,
            )
        )
        if self.transport is None:
            raise RuntimeError("live Pipedrive mode requires an injected transport")
        return self.transport.request(method, path, json=payload)
