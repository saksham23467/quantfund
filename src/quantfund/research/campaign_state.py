"""Campaign and candidate finite-state machines — illegal transitions fail closed."""

from __future__ import annotations

from enum import Enum


class CampaignState(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    SEALING = "SEALING"
    TEST_PHASE = "TEST_PHASE"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"


class CandidateState(str, Enum):
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    DEDUPLICATED = "DEDUPLICATED"
    SCREENED = "SCREENED"
    VALIDATION_EVALUATED = "VALIDATION_EVALUATED"
    ROBUSTNESS_EVALUATED = "ROBUSTNESS_EVALUATED"
    WF_EVALUATED = "WF_EVALUATED"
    SEALED = "SEALED"
    TEST_EVALUATED = "TEST_EVALUATED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class IllegalStateTransition(ValueError):
    """Raised when a campaign/candidate transition is not allowed."""


_CAMPAIGN_TRANSITIONS: dict[CampaignState, frozenset[CampaignState]] = {
    CampaignState.DRAFT: frozenset({CampaignState.READY, CampaignState.FAILED}),
    CampaignState.READY: frozenset({CampaignState.RUNNING, CampaignState.FAILED}),
    CampaignState.RUNNING: frozenset(
        {CampaignState.SEALING, CampaignState.FAILED, CampaignState.FINALIZED}
    ),
    CampaignState.SEALING: frozenset({CampaignState.TEST_PHASE, CampaignState.FAILED}),
    CampaignState.TEST_PHASE: frozenset(
        {CampaignState.FINALIZED, CampaignState.FAILED}
    ),
    CampaignState.FINALIZED: frozenset(),
    CampaignState.FAILED: frozenset(),
}


_CANDIDATE_TRANSITIONS: dict[CandidateState, frozenset[CandidateState]] = {
    CandidateState.GENERATED: frozenset(
        {CandidateState.VALIDATED, CandidateState.REJECTED}
    ),
    CandidateState.VALIDATED: frozenset(
        {CandidateState.DEDUPLICATED, CandidateState.REJECTED}
    ),
    CandidateState.DEDUPLICATED: frozenset(
        {CandidateState.SCREENED, CandidateState.REJECTED}
    ),
    CandidateState.SCREENED: frozenset(
        {CandidateState.VALIDATION_EVALUATED, CandidateState.REJECTED}
    ),
    CandidateState.VALIDATION_EVALUATED: frozenset(
        {CandidateState.ROBUSTNESS_EVALUATED, CandidateState.REJECTED}
    ),
    CandidateState.ROBUSTNESS_EVALUATED: frozenset(
        {
            CandidateState.WF_EVALUATED,
            CandidateState.SEALED,
            CandidateState.REJECTED,
        }
    ),
    CandidateState.WF_EVALUATED: frozenset(
        {CandidateState.SEALED, CandidateState.REJECTED}
    ),
    CandidateState.SEALED: frozenset(
        {CandidateState.TEST_EVALUATED, CandidateState.REJECTED}
    ),
    CandidateState.TEST_EVALUATED: frozenset(
        {CandidateState.ACCEPTED, CandidateState.REJECTED}
    ),
    CandidateState.ACCEPTED: frozenset(),
    CandidateState.REJECTED: frozenset(),
}


def transition_campaign(current: CampaignState, target: CampaignState) -> CampaignState:
    allowed = _CAMPAIGN_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise IllegalStateTransition(
            f"Illegal campaign transition {current.value} → {target.value}"
        )
    return target


def transition_candidate(
    current: CandidateState, target: CandidateState
) -> CandidateState:
    allowed = _CANDIDATE_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise IllegalStateTransition(
            f"Illegal candidate transition {current.value} → {target.value}"
        )
    return target


def can_transition_campaign(current: CampaignState, target: CampaignState) -> bool:
    return target in _CAMPAIGN_TRANSITIONS.get(current, frozenset())


def can_transition_candidate(current: CandidateState, target: CandidateState) -> bool:
    return target in _CANDIDATE_TRANSITIONS.get(current, frozenset())
