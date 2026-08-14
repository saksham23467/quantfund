"""Phase 6 — config hashing, state machine, budgets."""

from __future__ import annotations

from datetime import date

import pytest

from quantfund.research.campaign import CampaignPurpose, ResearchCampaignConfig
from quantfund.research.campaign_state import (
    CampaignState,
    CandidateState,
    IllegalStateTransition,
    can_transition_campaign,
    transition_campaign,
    transition_candidate,
)
from quantfund.research.search_space import BudgetExceededError, CampaignBudgets
from quantfund.research.splits import Period, SplitConfig


def _split() -> SplitConfig:
    return SplitConfig(
        train=Period(start=date(2024, 1, 2), end=date(2024, 1, 10)),
        validation=Period(start=date(2024, 1, 11), end=date(2024, 1, 18)),
        test=Period(start=date(2024, 1, 19), end=date(2024, 1, 25)),
    )


def _cfg(**kwargs) -> ResearchCampaignConfig:
    base = dict(
        dataset_id="d",
        dataset_version="v1",
        universe_id="u",
        universe_version="uv",
        split_config=_split(),
        candidate_budget=20,
        experiment_budget=40,
    )
    base.update(kwargs)
    return ResearchCampaignConfig(**base)


def test_config_hash_deterministic():
    a = _cfg(campaign_id="aaa", random_seed=1)
    b = _cfg(campaign_id="bbb", random_seed=1)
    assert a.compute_hash() == b.compute_hash()


def test_config_hash_changes_with_material_field():
    a = _cfg(random_seed=1)
    b = _cfg(random_seed=2)
    assert a.compute_hash() != b.compute_hash()


def test_config_hash_ignores_created_at_and_campaign_id():
    a = _cfg(campaign_id="x", created_at="2020-01-01T00:00:00+00:00")
    b = _cfg(campaign_id="y", created_at="2025-01-01T00:00:00+00:00")
    assert a.compute_hash() == b.compute_hash()


def test_config_immutable():
    c = _cfg()
    with pytest.raises(Exception):
        c.candidate_budget = 99  # type: ignore[misc]


def test_score_policy_v1_only():
    c = _cfg(score_policy_version="score_policy_v2")
    with pytest.raises(ValueError, match="score_policy_v1"):
        c.assert_score_policy_v1()


def test_campaign_purposes_c1():
    assert CampaignPurpose.EXPLORATORY_DEVELOPMENT.value == "exploratory_development"
    assert CampaignPurpose.RESEARCH.value == "research"
    assert set(CampaignPurpose) == {
        CampaignPurpose.EXPLORATORY_DEVELOPMENT,
        CampaignPurpose.RESEARCH,
    }


def test_campaign_valid_transitions():
    assert transition_campaign(CampaignState.DRAFT, CampaignState.READY) == CampaignState.READY
    assert transition_campaign(CampaignState.READY, CampaignState.RUNNING) == CampaignState.RUNNING
    assert transition_campaign(CampaignState.RUNNING, CampaignState.SEALING) == CampaignState.SEALING
    assert (
        transition_campaign(CampaignState.SEALING, CampaignState.TEST_PHASE)
        == CampaignState.TEST_PHASE
    )
    assert (
        transition_campaign(CampaignState.TEST_PHASE, CampaignState.FINALIZED)
        == CampaignState.FINALIZED
    )


def test_campaign_illegal_draft_to_test():
    with pytest.raises(IllegalStateTransition):
        transition_campaign(CampaignState.DRAFT, CampaignState.TEST_PHASE)


def test_campaign_illegal_running_to_test():
    with pytest.raises(IllegalStateTransition):
        transition_campaign(CampaignState.RUNNING, CampaignState.TEST_PHASE)


def test_campaign_finalized_terminal():
    assert not can_transition_campaign(CampaignState.FINALIZED, CampaignState.RUNNING)
    with pytest.raises(IllegalStateTransition):
        transition_campaign(CampaignState.FINALIZED, CampaignState.RUNNING)


def test_candidate_valid_and_reject_paths():
    s = CandidateState.GENERATED
    s = transition_candidate(s, CandidateState.VALIDATED)
    s = transition_candidate(s, CandidateState.DEDUPLICATED)
    s = transition_candidate(s, CandidateState.SCREENED)
    s = transition_candidate(s, CandidateState.REJECTED)
    assert s == CandidateState.REJECTED


def test_candidate_no_second_test_eval_transition():
    with pytest.raises(IllegalStateTransition):
        transition_candidate(CandidateState.TEST_EVALUATED, CandidateState.TEST_EVALUATED)


def test_candidate_sealed_cannot_rerun_validation():
    with pytest.raises(IllegalStateTransition):
        transition_candidate(CandidateState.SEALED, CandidateState.VALIDATION_EVALUATED)


def test_budget_candidate_limit():
    b = CampaignBudgets(max_candidates=2, max_experiments=10)
    b.consume_candidate()
    b.consume_candidate()
    with pytest.raises(BudgetExceededError):
        b.consume_candidate()


def test_budget_experiment_limit():
    b = CampaignBudgets(max_candidates=10, max_experiments=2)
    b.consume_experiment()
    b.consume_experiment()
    with pytest.raises(BudgetExceededError):
        b.consume_experiment()


def test_budget_monotonic_no_reset():
    b = CampaignBudgets(max_candidates=5, max_experiments=5)
    b.consume_candidate()
    b.consume_experiment()
    with pytest.raises(ValueError, match="cannot decrease"):
        b.restore(candidates_consumed=0, experiments_consumed=1)


def test_budget_resume_restore_forward_only():
    b = CampaignBudgets(max_candidates=20, max_experiments=40)
    b.consume_candidate()
    b.restore(candidates_consumed=5, experiments_consumed=3)
    assert b.snapshot()["candidates_consumed"] == 5
    assert b.snapshot()["experiments_consumed"] == 3
