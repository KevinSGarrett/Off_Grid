from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.domain.states import IntegrationMode


@dataclass(frozen=True)
class GoogleWorkspaceAdapter:
    mode: IntegrationMode

    def preview_report(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return {"mode": self.mode.value, "preview": dict(payload), "external_write": False}

    @staticmethod
    def forms_response_submission_supported() -> bool:
        # Google Forms API exposes response get/list, not a create/submit-response method.
        return False
