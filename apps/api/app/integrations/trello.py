from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.domain.states import IntegrationMode


@dataclass(frozen=True)
class TrelloAdapter:
    mode: IntegrationMode

    def preview_task(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return {"mode": self.mode.value, "preview": dict(payload), "external_write": False}
