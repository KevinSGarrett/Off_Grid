import pytest

from app.domain.errors import InvalidStateTransition
from app.domain.states import CRMPromotionState, ContactState, ProjectState
from app.services.state_machine import CRM_TRANSITIONS, CONTACT_TRANSITIONS, PROJECT_TRANSITIONS, require_transition


def test_project_happy_path_transition_is_explicit() -> None:
    assert require_transition(ProjectState.INGESTED, ProjectState.PARSED, PROJECT_TRANSITIONS) is ProjectState.PARSED


def test_project_cannot_jump_directly_to_crm_ready() -> None:
    with pytest.raises(InvalidStateTransition):
        require_transition(ProjectState.INGESTED, ProjectState.CRM_READY, PROJECT_TRANSITIONS)


def test_contact_cannot_jump_to_authority_verified() -> None:
    with pytest.raises(InvalidStateTransition):
        require_transition(ContactState.DISCOVERED, ContactState.AUTHORITY_VERIFIED, CONTACT_TRANSITIONS)


def test_crm_deal_requires_lead_state_first() -> None:
    with pytest.raises(InvalidStateTransition):
        require_transition(CRMPromotionState.INTELLIGENCE, CRMPromotionState.DEAL, CRM_TRANSITIONS)
