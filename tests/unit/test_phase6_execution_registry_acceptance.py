"""Phase 6 — cost/slippage wiring, registry events, acceptance gates."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from quantfund.data.models import MarketBar
from quantfund.research.acceptance import CampaignAcceptancePolicy
from quantfund.research.campaign import AcceptancePolicy, CampaignPurpose
from quantfund.research.campaign_state import CandidateState
from quantfund.research.candidate_pool import CandidateRecord
from quantfund.research.execution_models import (
    UnknownExecutionModelError,
    resolve_cost_model,
    resolve_slippage_model,
)
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.runner import ResearchRunner
from quantfund.research.splits import Period, SplitConfig
from quantfund.research.test_seal import CampaignTestSeal
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy
from quantfund.storage.registry import ExperimentRegistry


def _bars(n: int = 30) -> list[MarketBar]:
    out = []
    d = date(2024, 1, 2)
    p = 100.0
    while len(out) < n:
        if d.weekday() < 5:
            p += 0.5
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


def test_resolve_known_cost_and_slippage():
    c = resolve_cost_model("equity_delivery_v1")
    s = resolve_slippage_model("fixed_bps_5")
    assert c.name == "equity_delivery_v1"
    assert s.bps == 5.0


def test_unknown_cost_model_fails_closed():
    with pytest.raises(UnknownExecutionModelError):
        resolve_cost_model("not_a_real_model")


def test_unknown_slippage_model_fails_closed():
    with pytest.raises(UnknownExecutionModelError):
        resolve_slippage_model("bps_5")


def test_cost_slippage_change_economics():
    from quantfund.trading.models import OrderSide

    cost = resolve_cost_model("equity_delivery_v1")
    slip5 = resolve_slippage_model("fixed_bps_5")
    slip50 = resolve_slippage_model("fixed_bps_50")
    px5, _ = slip5.apply(side=OrderSide.BUY, price=100.0)
    px50, _ = slip50.apply(side=OrderSide.BUY, price=100.0)
    assert px50 > px5
    c5 = cost.compute(side=OrderSide.BUY, quantity=100, price=px5)
    # Higher price → higher turnover costs
    c50 = cost.compute(side=OrderSide.BUY, quantity=100, price=px50)
    assert c50.total > c5.total


def test_research_runner_unknown_cost_fails(tmp_path: Path):
    reg = ExperimentRegistry(tmp_path / "reg")
    runner = ResearchRunner(reg)
    bars = _bars()
    dates = [b.timestamp.date() for b in bars]
    cfg = ExperimentConfig(
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        dataset_id="d",
        dataset_version="v",
        universe_id="u",
        universe_version="uv",
        cost_model="totally_unknown",
        slippage_model="fixed_bps_5",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        split_config=SplitConfig(
            train=Period(start=dates[0], end=dates[9]),
            validation=Period(start=dates[10], end=dates[19]),
            test=Period(start=dates[20], end=dates[-1]),
        ),
        start_date=dates[0].isoformat(),
        end_date=dates[-1].isoformat(),
        initial_capital=100_000,
        research_eligibility="development_only",
    )
    with pytest.raises(UnknownExecutionModelError):
        runner.evaluate(
            strategy_factory=lambda: BuyAndHoldStrategy(symbol="TEST"),
            bars=bars,
            config=cfg,
            run_robustness=False,
            certified_eligibility="development_only",
        )


def test_campaign_events_append_only(tmp_path: Path):
    reg = ExperimentRegistry(tmp_path / "reg")
    reg.create_campaign(
        campaign_id="c1",
        config_hash="h",
        purpose="exploratory_development",
        state="DRAFT",
        config_json={"x": 1},
        created_at="2024-01-01T00:00:00+00:00",
    )
    id1 = reg.append_campaign_event(
        campaign_id="c1", event_type="a", payload={"n": 1}
    )
    id2 = reg.append_campaign_event(
        campaign_id="c1", event_type="b", payload={"n": 2}
    )
    assert id2 > id1
    events = reg.get_campaign_events("c1")
    assert len(events) >= 3  # created + a + b
    assert events[-1]["event_type"] == "b"
    # No replace API — historical event_id=id1 still present
    assert any(e["event_id"] == id1 for e in events)


def test_campaign_trial_counts_monotonic(tmp_path: Path):
    reg = ExperimentRegistry(tmp_path / "reg")
    reg.create_campaign(
        campaign_id="c2",
        config_hash="h",
        purpose="exploratory_development",
        state="DRAFT",
        config_json={},
        created_at="2024-01-01T00:00:00+00:00",
    )
    reg.bump_campaign_trials("c2", candidates=2, experiments=1)
    reg.bump_campaign_trials("c2", experiments=1, test_evaluations=1)
    counts = reg.count_campaign_trials("c2")
    assert counts["n_candidates"] == 2
    assert counts["n_experiments"] == 2
    assert counts["n_test_evaluations"] == 1


def test_duplicate_campaign_id_rejected(tmp_path: Path):
    reg = ExperimentRegistry(tmp_path / "reg")
    reg.create_campaign(
        campaign_id="dup",
        config_hash="h",
        purpose="exploratory_development",
        state="DRAFT",
        config_json={},
        created_at="2024-01-01T00:00:00+00:00",
    )
    with pytest.raises(FileExistsError):
        reg.create_campaign(
            campaign_id="dup",
            config_hash="h2",
            purpose="research",
            state="DRAFT",
            config_json={},
            created_at="2024-01-02T00:00:00+00:00",
        )


def test_acceptance_development_only_zero():
    policy = CampaignAcceptancePolicy(AcceptancePolicy())
    seal = CampaignTestSeal(
        campaign_id="c",
        config_hash="h",
        selection_criterion="validation_sharpe",
        score_policy_version="score_policy_v1",
        dataset_id="d",
        dataset_version="v",
        acceptance_policy_id="acceptance_policy_v1",
    )
    seal.sealed = True
    seal.frozen_candidate_ids = ["cand"]
    seal.test_evaluation_log = ["cand"]
    cand = CandidateRecord(
        candidate_id="cand",
        campaign_id="c",
        spec=None,
        strategy_hash="h",
        state=CandidateState.TEST_EVALUATED,
        genealogy={},
        test_evaluations=1,
    )
    d = policy.decide(
        candidate=cand,
        purpose=CampaignPurpose.EXPLORATORY_DEVELOPMENT,
        certified_eligibility="development_only",
        seal=seal,
        robustness_pass_rate=1.0,
        robustness_fragile=False,
        walkforward_enabled=False,
        walkforward_stats=None,
        score_accepted=True,
        score_rejection_reasons=[],
        trial_counts={"n_experiments": 1},
    )
    assert d.accepted is False
    assert any("development_only" in r for r in d.reasons)


def test_acceptance_fragile_rejected():
    policy = CampaignAcceptancePolicy(AcceptancePolicy())
    seal = CampaignTestSeal(
        campaign_id="c",
        config_hash="h",
        selection_criterion="validation_sharpe",
        score_policy_version="score_policy_v1",
        dataset_id="d",
        dataset_version="v",
        acceptance_policy_id="a",
    )
    seal.sealed = True
    seal.frozen_candidate_ids = ["cand"]
    seal.test_evaluation_log = ["cand"]
    cand = CandidateRecord(
        candidate_id="cand",
        campaign_id="c",
        spec=None,
        strategy_hash="h",
        state=CandidateState.TEST_EVALUATED,
        genealogy={},
        test_evaluations=1,
    )
    d = policy.decide(
        candidate=cand,
        purpose=CampaignPurpose.RESEARCH,
        certified_eligibility="research_eligible",
        seal=seal,
        robustness_pass_rate=0.2,
        robustness_fragile=True,
        walkforward_enabled=False,
        walkforward_stats=None,
        score_accepted=True,
        score_rejection_reasons=[],
        trial_counts={"n_experiments": 1},
    )
    assert d.accepted is False
    assert any("robustness" in r for r in d.reasons)


def test_acceptance_score_cannot_override_hard_reject():
    policy = CampaignAcceptancePolicy(AcceptancePolicy())
    seal = CampaignTestSeal(
        campaign_id="c",
        config_hash="h",
        selection_criterion="validation_sharpe",
        score_policy_version="score_policy_v1",
        dataset_id="d",
        dataset_version="v",
        acceptance_policy_id="a",
    )
    # not sealed
    cand = CandidateRecord(
        candidate_id="cand",
        campaign_id="c",
        spec=None,
        strategy_hash="h",
        state=CandidateState.TEST_EVALUATED,
        genealogy={},
        test_evaluations=1,
    )
    d = policy.decide(
        candidate=cand,
        purpose=CampaignPurpose.RESEARCH,
        certified_eligibility="research_eligible",
        seal=seal,
        robustness_pass_rate=1.0,
        robustness_fragile=False,
        walkforward_enabled=False,
        walkforward_stats=None,
        score_accepted=True,
        score_rejection_reasons=[],
        trial_counts={"n_experiments": 1},
    )
    assert d.accepted is False
    assert "campaign_not_sealed" in d.reasons
