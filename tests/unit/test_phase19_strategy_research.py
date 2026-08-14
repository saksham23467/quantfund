"""Regression tests for the controlled Phase 19 strategy-research framework.

Covers:
- Fail-closed prerequisite: no search runs unless research eligibility is TRUE.
- Full funnel via an injected evaluator (validation → OOS → robustness → DSR).
- Per-candidate data-integrity gate (PIT / RAW / costs / slippage / timing / no
  look-ahead / no survivorship).
- No auto-promotion of the best strategy.
- Preserved DSR trial accounting and fixed research budget.
- Safety: never enables paper/live trading or submits orders.
"""

from __future__ import annotations

import pytest

from quantfund.research.strategy_research import (
    CostModel,
    DataIntegrityRequirements,
    EvaluationOutput,
    FailClosedEvaluator,
    GatePolicy,
    Period,
    ResearchContext,
    SplitMetrics,
    StrategyFamily,
    evaluate_prerequisite,
    run_strategy_research,
)
from quantfund.research.strategy_research.gates import (
    dsr_gate,
    oos_gate,
    robustness_gate,
    validation_gate,
)

ELIGIBLE_P18 = {"research_eligible": True, "stopped_at_blocker": None}
ELIGIBLE_PIT = {"research_eligibility": True, "blockers": []}
INELIGIBLE_P18 = {
    "research_eligible": False,
    "stopped_at_blocker": "exchange_grade_source_certification",
}
INELIGIBLE_PIT = {
    "research_eligibility": False,
    "blockers": ["missing_pit_membership_ledger"],
    "membership_coverage_ratio": 0.0,
    "unknown_membership_count": 17064,
}


def _context() -> ResearchContext:
    return ResearchContext(
        dataset_id="ds_test",
        dataset_version="v1",
        dataset_hash="sha256:deadbeef",
        universe_id="u_test",
        universe_version="uv1",
        train_period=Period("2018-01-01", "2021-12-31"),
        validation_period=Period("2022-01-01", "2023-12-31"),
        test_period=Period("2024-01-01", "2025-12-31"),
        cost_model=CostModel(
            model_id="equity_delivery_v1",
            transaction_cost_bps=10.0,
            slippage_bps=5.0,
            execution_timing="next_open_raw",
        ),
    )


def _metrics(sharpe: float, *, n_obs: int = 756, n_trades: int = 50, dd: float = 0.1):
    return SplitMetrics(
        n_obs=n_obs,
        n_trades=n_trades,
        total_return=0.4,
        cagr=0.12,
        sharpe=sharpe,
        sortino=sharpe * 1.2,
        max_drawdown=dd,
        turnover=1.5,
        exposure=0.6,
        win_rate=0.55,
        profit_factor=1.4,
    )


class _FakeEvaluator:
    """Deterministic evaluator for tests — never touches real data or trading."""

    def __init__(
        self,
        *,
        integrity_ok: bool = True,
        sharpe: float = 3.0,
        n_obs: int = 756,
        n_trades: int = 50,
        drawdown: float = 0.1,
        robustness_pass_rate: float = 1.0,
        fragile: bool = False,
    ) -> None:
        self.integrity_ok = integrity_ok
        self.sharpe = sharpe
        self.n_obs = n_obs
        self.n_trades = n_trades
        self.drawdown = drawdown
        self.robustness_pass_rate = robustness_pass_rate
        self.fragile = fragile

    def evaluate(self, spec, context) -> EvaluationOutput:
        if not self.integrity_ok:
            return EvaluationOutput(
                data_integrity=DataIntegrityRequirements(
                    point_in_time_universe=False,
                    exchange_grade_data=False,
                    raw_execution_prices=False,
                    transaction_costs_modeled=False,
                    slippage_modeled=False,
                    realistic_execution_timing=False,
                    no_look_ahead=False,
                    no_survivorship_bias=False,
                )
            )
        m = _metrics(self.sharpe, n_obs=self.n_obs, n_trades=self.n_trades, dd=self.drawdown)
        return EvaluationOutput(
            data_integrity=DataIntegrityRequirements(
                point_in_time_universe=True,
                exchange_grade_data=True,
                raw_execution_prices=True,
                transaction_costs_modeled=True,
                slippage_modeled=True,
                realistic_execution_timing=True,
                no_look_ahead=True,
                no_survivorship_bias=True,
            ),
            metrics_by_split={"train": m, "validation": m, "test": m},
            robustness_pass_rate=self.robustness_pass_rate,
            robustness_fragile=self.fragile,
            oos_n_obs=self.n_obs,
        )


# --------------------------------------------------------------------------
# Prerequisite (fail closed)
# --------------------------------------------------------------------------


def test_prerequisite_false_when_phase18_ineligible():
    pre = evaluate_prerequisite(phase18_payload=INELIGIBLE_P18, pit_payload=ELIGIBLE_PIT)
    assert pre.research_eligible is False
    assert any("phase18_research_eligible=false" in b for b in pre.blockers)


def test_prerequisite_false_when_pit_ineligible():
    pre = evaluate_prerequisite(phase18_payload=ELIGIBLE_P18, pit_payload=INELIGIBLE_PIT)
    assert pre.research_eligible is False
    assert any("pit_universe:" in b for b in pre.blockers)


def test_prerequisite_false_when_verdict_missing():
    pre = evaluate_prerequisite(phase18_payload=None, pit_payload=None)
    assert pre.research_eligible is False
    assert "phase18_eligibility_verdict_missing" in pre.blockers
    assert "pit_universe_coverage_verdict_missing" in pre.blockers


def test_prerequisite_true_only_when_both_true():
    pre = evaluate_prerequisite(phase18_payload=ELIGIBLE_P18, pit_payload=ELIGIBLE_PIT)
    assert pre.research_eligible is True
    assert pre.blockers == []


# --------------------------------------------------------------------------
# Search does NOT run when prerequisite fails
# --------------------------------------------------------------------------


def test_search_halts_when_ineligible():
    result = run_strategy_research(
        phase18_payload=INELIGIBLE_P18,
        pit_payload=INELIGIBLE_PIT,
        context=_context(),
        evaluator=_FakeEvaluator(),
    )
    assert result.ran_search is False
    assert result.stopped_reason == "research_eligibility_false"
    funnel = result.funnel()
    assert funnel["candidates_tested"] == 0
    assert funnel["final_accepted_candidates"] == 0
    assert result.trial_count == 0
    assert result.records == []


def test_search_halts_even_with_good_evaluator_if_ineligible():
    """A strong evaluator must not override the eligibility prerequisite."""
    result = run_strategy_research(
        phase18_payload=INELIGIBLE_P18,
        pit_payload=ELIGIBLE_PIT,
        context=_context(),
        evaluator=_FakeEvaluator(sharpe=5.0),
    )
    assert result.ran_search is False
    assert result.funnel()["final_accepted_candidates"] == 0


# --------------------------------------------------------------------------
# Full funnel when eligible (via injected evaluator)
# --------------------------------------------------------------------------


def test_full_funnel_accepts_strong_candidates_but_never_promotes():
    result = run_strategy_research(
        phase18_payload=ELIGIBLE_P18,
        pit_payload=ELIGIBLE_PIT,
        context=_context(),
        evaluator=_FakeEvaluator(sharpe=3.0),
        families=[StrategyFamily.MEAN_REVERSION],  # 4 candidates
    )
    assert result.ran_search is True
    funnel = result.funnel()
    assert funnel["candidates_tested"] == 4
    assert funnel["candidates_passing_validation"] == 4
    assert funnel["candidates_passing_oos"] == 4
    assert funnel["candidates_passing_robustness"] == 4
    assert funnel["candidates_passing_dsr"] == 4
    assert funnel["final_accepted_candidates"] == 4
    # No auto-promotion — accepted != promoted.
    assert all(r.promoted is False for r in result.records)
    assert all(r.accepted for r in result.records)


def test_data_integrity_failure_rejects_all_candidates():
    result = run_strategy_research(
        phase18_payload=ELIGIBLE_P18,
        pit_payload=ELIGIBLE_PIT,
        context=_context(),
        evaluator=_FakeEvaluator(integrity_ok=False),
        families=[StrategyFamily.TREND_FOLLOWING],
    )
    funnel = result.funnel()
    assert funnel["candidates_tested"] == 4
    assert funnel["candidates_rejected"] == 4
    assert funnel["final_accepted_candidates"] == 0
    assert all(r.stage_reached == "data_integrity" for r in result.records)
    for r in result.records:
        assert "data_integrity:point_in_time_universe" in r.rejection_reasons
        assert "data_integrity:raw_execution_prices" in r.rejection_reasons


def test_weak_sharpe_rejected_at_validation():
    result = run_strategy_research(
        phase18_payload=ELIGIBLE_P18,
        pit_payload=ELIGIBLE_PIT,
        context=_context(),
        evaluator=_FakeEvaluator(sharpe=0.1),
        families=[StrategyFamily.BREAKOUT],
    )
    funnel = result.funnel()
    assert funnel["candidates_passing_validation"] == 0
    assert funnel["final_accepted_candidates"] == 0


def test_fragile_robustness_rejected():
    result = run_strategy_research(
        phase18_payload=ELIGIBLE_P18,
        pit_payload=ELIGIBLE_PIT,
        context=_context(),
        evaluator=_FakeEvaluator(sharpe=3.0, fragile=True),
        families=[StrategyFamily.MOMENTUM],
    )
    funnel = result.funnel()
    assert funnel["candidates_passing_oos"] >= 1
    assert funnel["candidates_passing_robustness"] == 0
    assert funnel["final_accepted_candidates"] == 0


# --------------------------------------------------------------------------
# DSR trial accounting + budget
# --------------------------------------------------------------------------


def test_dsr_trial_count_equals_experiments_consumed():
    result = run_strategy_research(
        phase18_payload=ELIGIBLE_P18,
        pit_payload=ELIGIBLE_PIT,
        context=_context(),
        evaluator=_FakeEvaluator(sharpe=3.0),
        families=[StrategyFamily.MEAN_REVERSION],
    )
    assert result.trial_count == result.budget["experiments_consumed"]
    assert result.trial_count == 4
    assert all(r.trial_count == 4 for r in result.records)
    assert all(r.deflated_sharpe is not None for r in result.records)


def test_fixed_budget_caps_candidates():
    result = run_strategy_research(
        phase18_payload=ELIGIBLE_P18,
        pit_payload=ELIGIBLE_PIT,
        context=_context(),
        evaluator=_FakeEvaluator(sharpe=3.0),
        max_candidates=3,
        max_experiments=3,
    )
    assert result.funnel()["candidates_tested"] == 3
    assert result.budget["candidates_consumed"] == 3


# --------------------------------------------------------------------------
# Gate unit checks
# --------------------------------------------------------------------------


def test_dsr_gate_rejects_undefined_and_below_floor():
    policy = GatePolicy()
    assert dsr_gate(None, policy) == ["dsr:undefined"]
    assert dsr_gate(0.5, policy) == ["dsr:below_floor"]
    assert dsr_gate(0.99, policy) == []


def test_validation_and_oos_gates_enforce_floors():
    policy = GatePolicy()
    weak = _metrics(0.1)
    assert "validation:sharpe_below_floor" in validation_gate(weak, policy)
    deep_dd = _metrics(1.0, dd=0.9)
    assert "oos:drawdown_exceeds_max" in oos_gate(deep_dd, policy)


def test_robustness_gate_rejects_fragile_and_low_pass_rate():
    policy = GatePolicy()
    assert "robustness:fragile" in robustness_gate(1.0, True, policy)
    assert "robustness:pass_rate_below_floor" in robustness_gate(0.1, False, policy)


# --------------------------------------------------------------------------
# Default evaluator fails closed
# --------------------------------------------------------------------------


def test_default_evaluator_fails_closed_on_data_integrity():
    result = run_strategy_research(
        phase18_payload=ELIGIBLE_P18,
        pit_payload=ELIGIBLE_PIT,
        context=_context(),
        evaluator=FailClosedEvaluator(),
        families=[StrategyFamily.VOLATILITY_REGIME],
    )
    assert result.funnel()["final_accepted_candidates"] == 0
    assert all(r.rejected for r in result.records)


# --------------------------------------------------------------------------
# End-to-end runner honesty on the real repository state
# --------------------------------------------------------------------------


def test_runner_fails_closed_and_writes_reports(tmp_path):
    from quantfund.research.strategy_research.runner import (
        run_phase19_strategy_research,
    )

    reports = tmp_path / "reports"
    docs = tmp_path / "docs"
    # Provide an ineligible PIT verdict so we don't trigger a full phase18 run.
    reports.mkdir(parents=True)
    (reports / "pit_universe_coverage.json").write_text(
        '{"research_eligibility": false, "blockers": ["missing_pit_membership_ledger"]}',
        encoding="utf-8",
    )
    (reports / "phase18_dataset_eligibility.json").write_text(
        '{"research_eligible": false, "stopped_at_blocker": "exchange_grade_source_certification"}',
        encoding="utf-8",
    )
    payload = run_phase19_strategy_research(reports_dir=reports, docs_dir=docs)
    assert payload["ran_search"] is False
    assert payload["funnel"]["final_accepted_candidates"] == 0
    assert payload["auto_promotion"]["enabled"] is False
    assert payload["safety"]["orders_submitted"] == 0
    assert payload["safety"]["live_trading"] == "DISABLED"
    assert (reports / "phase19_strategy_search.json").exists()
    assert (docs / "PHASE19_STRATEGY_RESEARCH.md").exists()
