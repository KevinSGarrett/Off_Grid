from __future__ import annotations

from collections.abc import Mapping, Set
from enum import Enum
from typing import TypeVar

from app.domain.errors import InvalidStateTransition
from app.domain.states import CRMPromotionState, ContactState, ProjectState

StateT = TypeVar("StateT", bound=Enum)

PROJECT_TRANSITIONS: Mapping[ProjectState, Set[ProjectState]] = {
    ProjectState.INGESTED: {ProjectState.PARSED},
    ProjectState.PARSED: {ProjectState.VALIDATED},
    ProjectState.VALIDATED: {ProjectState.QUALIFIED},
    ProjectState.QUALIFIED: {ProjectState.ACCOUNT_RESOLVED},
    ProjectState.ACCOUNT_RESOLVED: {ProjectState.CONTACT_RESOLUTION},
    ProjectState.CONTACT_RESOLUTION: {ProjectState.CRM_READY},
    ProjectState.CRM_READY: {ProjectState.ACTIVE_LEAD},
    ProjectState.ACTIVE_LEAD: {ProjectState.DEMO},
    ProjectState.DEMO: {ProjectState.WON, ProjectState.LOST},
    ProjectState.WON: set(),
    ProjectState.LOST: set(),
}

CONTACT_TRANSITIONS: Mapping[ContactState, Set[ContactState]] = {
    ContactState.DISCOVERED: {ContactState.EMPLOYMENT_VERIFIED},
    ContactState.EMPLOYMENT_VERIFIED: {ContactState.PROJECT_ASSOCIATION_VERIFIED},
    ContactState.PROJECT_ASSOCIATION_VERIFIED: {ContactState.ROLE_RELEVANT},
    ContactState.ROLE_RELEVANT: {ContactState.AUTHORITY_VERIFIED},
    ContactState.AUTHORITY_VERIFIED: set(),
}

CRM_TRANSITIONS: Mapping[CRMPromotionState, Set[CRMPromotionState]] = {
    CRMPromotionState.INTELLIGENCE: {CRMPromotionState.LEAD},
    CRMPromotionState.LEAD: {CRMPromotionState.DEAL},
    CRMPromotionState.DEAL: set(),
}


def require_transition(current: StateT, target: StateT, transitions: Mapping[StateT, Set[StateT]]) -> StateT:
    """Return target when transition is allowed; otherwise fail closed.

    Guard predicates (reconciliation, readiness, verification evidence) are added by
    owner waves before this structural transition is invoked.
    """
    allowed = transitions.get(current, set())
    if target not in allowed:
        raise InvalidStateTransition(f"Transition {current.value} -> {target.value} is not allowed")
    return target
