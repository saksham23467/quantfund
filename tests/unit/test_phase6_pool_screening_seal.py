"""Phase 6 — candidate pool, screening TRAIN-only, test seal."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from quantfund.ai.mock_generator import MockStrategyGenerator
from quantfund.ai.models import GenerationRequest
from quantfund.data.models import MarketBar
from quantfund.research.campaign_state import CandidateState, CampaignState
from quantfund.research.candidate_pool import CandidatePool
from quantfund.research.screening import ScreeningPolicy, screen_on_train
from quantfund.research.search_space import CampaignBudgets
from quantfund.research.splits import ChronologicalSplit, Period, SealedTestSetError, SplitConfig
from quantfund.research.test_seal import CampaignTestSeal, SealViolationError, assert_test_inaccessible
from quantfund.strategies.spec.interpret import interpret_strategy_spec


def _bars(n: int = 40) -> list[MarketBar]:
    out = []
    d = date(2024, 1, 2)
    p = 100.0
    while len(out) < n:
        if d.weekday() < 5:
            p += 0.2
            out.append(
                MarketBar(
                    timestamp=datetime(d.year, d.month, d.day),
                    symbol="TEST",
                    open=p,
                    high=p + 1,
                    low=p - 1,
                    close=p,
                    volume=1000,
                )
            )
        d += timedelta(days=1)
    return out


def _split(bars: list[MarketBar]) -> SplitConfig:
    dates = [b.timestamp.date() for b in bars]
    return SplitConfig(
        train=Period(start=dates[0], end=dates[14]),
        validation=Period(start=dates[15], end=dates[24]),
        test=Period(start=dates[25], end=dates[-1]),
    )


def test_pool_validation_hash_dedupe_genealogy():
    budgets = CampaignBudgets(max_candidates=20, max_experiments=40)
    pool = CandidatePool(campaign_id="camp1", budgets=budgets)
    gen = MockStrategyGenerator()
    specs = gen.generate(
        GenerationRequest(
            universe_id="u",
            symbol="TEST",
            number_of_candidates=8,
            random_seed=1,
            include_malformed_fixtures=True,
            family_id="f1",
        )
    )
    # Force a duplicate
    if len(specs) >= 2 and hasattr(specs[0], "model_copy"):
        specs.append(specs[0].model_copy(deep=True))
    pool.admit_generated(specs, family_id="f1", generator_type="mock")
    assert pool.stats.generated_count >= 8
    assert pool.stats.invalid_count >= 1
    unique = [c for c in pool.candidates if c.strategy_hash and not c.is_duplicate]
    assert unique
    assert unique[0].genealogy.get("campaign_id") == "camp1"
    assert unique[0].genealogy.get("candidate_id")


def test_pool_candidate_budget_hard_stop():
    budgets = CampaignBudgets(max_candidates=3, max_experiments=40)
    pool = CandidatePool(campaign_id="c", budgets=budgets)
    gen = MockStrategyGenerator()
    specs = gen.generate(
        GenerationRequest(
            universe_id="u",
            symbol="TEST",
            number_of_candidates=10,
            random_seed=2,
            include_malformed_fixtures=False,
            family_id="f",
        )
    )
    pool.admit_generated(specs, family_id="f")
    assert budgets.candidates_consumed == 3
    assert len(pool.candidates) == 3


def test_screening_train_only_and_reproducible():
    bars = _bars()
    split = _split(bars)
    gen = MockStrategyGenerator()
    specs = gen.generate(
        GenerationRequest(
            universe_id="u",
            symbol="TEST",
            number_of_candidates=1,
            random_seed=3,
            include_malformed_fixtures=False,
            family_id="f",
        )
    )
    strategy = interpret_strategy_spec(specs[0])
    policy = ScreeningPolicy(min_trades=1, max_drawdown=0.99)
    r1 = screen_on_train(
        strategy=strategy,
        bars=bars,
        split_config=split,
        policy=policy,
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        initial_capital=100_000,
        dataset_id="d",
        dataset_version="v",
        research_eligibility="development_only",
    )
    r2 = screen_on_train(
        strategy=strategy,
        bars=bars,
        split_config=split,
        policy=policy,
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        initial_capital=100_000,
        dataset_id="d",
        dataset_version="v",
        research_eligibility="development_only",
    )
    assert r1.to_dict() == r2.to_dict()
    assert r1.validation_accessed is False
    assert r1.test_accessed is False
    # TEST still sealed
    cs = ChronologicalSplit.from_bars(bars, split)
    with pytest.raises(SealedTestSetError):
        cs.get_test_bars()


def test_screening_policy_versioned_defaults():
    p = ScreeningPolicy()
    assert p.policy_id == "screening_policy_v1"
    assert p.min_trades == 5
    assert p.max_drawdown == 0.40


def test_seal_blocks_premature_test_and_second_test():
    seal_early = CampaignTestSeal(
        campaign_id="c",
        config_hash="h",
        selection_criterion="validation_sharpe",
        score_policy_version="score_policy_v1",
        dataset_id="d",
        dataset_version="v",
        acceptance_policy_id="acceptance_policy_v1",
    )
    with pytest.raises(SealViolationError):
        seal_early.authorize_test_evaluation(
            candidate_id="x",
            candidate_state=CandidateState.SEALED,
            prior_test_evaluations=0,
        )

    seal = CampaignTestSeal(
        campaign_id="c2",
        config_hash="h",
        selection_criterion="validation_sharpe",
        score_policy_version="score_policy_v1",
        dataset_id="d",
        dataset_version="v",
        acceptance_policy_id="acceptance_policy_v1",
    )
    seal.seal(
        campaign_state=CampaignState.SEALING,
        candidate_ids=["x"],
        trial_counters={"n_experiments": 1},
        selection_criterion="validation_sharpe",
        config_hash="h",
    )
    seal.authorize_test_evaluation(
        candidate_id="x",
        candidate_state=CandidateState.SEALED,
        prior_test_evaluations=0,
    )
    with pytest.raises(SealViolationError, match="Second TEST"):
        seal.authorize_test_evaluation(
            candidate_id="x",
            candidate_state=CandidateState.SEALED,
            prior_test_evaluations=1,
        )


def test_seal_freezes_config_and_selection_and_candidates():
    seal = CampaignTestSeal(
        campaign_id="c",
        config_hash="h1",
        selection_criterion="validation_sharpe",
        score_policy_version="score_policy_v1",
        dataset_id="d",
        dataset_version="v",
        acceptance_policy_id="a",
    )
    seal.seal(
        campaign_state=CampaignState.SEALING,
        candidate_ids=["a"],
        trial_counters={},
        selection_criterion="validation_sharpe",
        config_hash="h1",
    )
    with pytest.raises(SealViolationError):
        seal.assert_can_add_candidates()
    with pytest.raises(SealViolationError):
        seal.assert_can_change_selection_criterion("other")
    with pytest.raises(SealViolationError):
        seal.assert_can_change_config("h2")


def test_assert_test_inaccessible():
    bars = _bars(30)
    split_cfg = _split(bars)
    split = ChronologicalSplit.from_bars(bars, split_cfg)
    assert_test_inaccessible(split)
