from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.domain.states import VerificationState
from app.scoring.config import LoadedConfig, load_yaml_config


_STATE_ORDER = {
    VerificationState.UNKNOWN: 0,
    VerificationState.SUPPORTED: 1,
    VerificationState.VERIFIED: 2,
}


@dataclass(frozen=True)
class SourceRule:
    priority: int
    max_state: VerificationState


class SourcePrecedencePolicy:
    """Attribute-specific authority policy for external evidence.

    A source may be strong for one question and weak for another. This class deliberately
    refuses to apply a single global source ranking to employment, project association,
    role relevance, and rental authority.
    """

    def __init__(self, path: str | Path = "config/source_precedence.yaml"):
        self.loaded: LoadedConfig = load_yaml_config(path)
        self.data = self.loaded.data
        self.policy = self.data["policy"]
        self.attributes = self.data["attributes"]

    @property
    def version(self) -> str:
        return str(self.policy["version"])

    def rule_for(self, attribute: str, source_type: str) -> SourceRule:
        attr = self.attributes.get(attribute)
        if not isinstance(attr, dict):
            return SourceRule(priority=0, max_state=VerificationState.UNKNOWN)
        source = attr.get("sources", {}).get(source_type)
        if not isinstance(source, dict):
            return SourceRule(priority=0, max_state=VerificationState.UNKNOWN)
        return SourceRule(
            priority=int(source.get("priority", 0)),
            max_state=VerificationState(str(source.get("max_state", "UNKNOWN"))),
        )

    @staticmethod
    def cap_state(requested: VerificationState, maximum: VerificationState) -> VerificationState:
        if requested in {VerificationState.CONFLICTED, VerificationState.REJECTED}:
            return requested
        if maximum in {VerificationState.CONFLICTED, VerificationState.REJECTED}:
            return maximum
        req = _STATE_ORDER.get(requested, 0)
        cap = _STATE_ORDER.get(maximum, 0)
        target = min(req, cap)
        for state, rank in _STATE_ORDER.items():
            if rank == target:
                return state
        return VerificationState.UNKNOWN

    def aggregate(self, attribute: str, evidence: Iterable[tuple[str, VerificationState]]) -> tuple[VerificationState, int, tuple[str, ...]]:
        states: list[VerificationState] = []
        priorities: list[int] = []
        source_types: list[str] = []
        for source_type, requested in evidence:
            rule = self.rule_for(attribute, source_type)
            capped = self.cap_state(requested, rule.max_state)
            states.append(capped)
            priorities.append(rule.priority)
            source_types.append(source_type)
        if not states:
            return VerificationState.UNKNOWN, 0, tuple()
        if VerificationState.CONFLICTED in states:
            return VerificationState.CONFLICTED, max(priorities, default=0), tuple(sorted(set(source_types)))
        if VerificationState.VERIFIED in states:
            final = VerificationState.VERIFIED
        elif VerificationState.SUPPORTED in states:
            final = VerificationState.SUPPORTED
        elif VerificationState.REJECTED in states:
            final = VerificationState.REJECTED
        else:
            final = VerificationState.UNKNOWN
        return final, max(priorities, default=0), tuple(sorted(set(source_types)))
