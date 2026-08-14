"""Performance metrics and edge-case tests."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from quantfund.analytics.metrics import _max_drawdown, compute_metrics
from quantfund.backtest.engine import BacktestResult
from quantfund.backtest.portfolio import EquityPoint, Portfolio


def _empty_result(equity_points: list[EquityPoint] | None = None) -> BacktestResult:
    port = Portfolio(cash=100_000)
    if equity_points:
        port.equity_curve = equity_points
    return BacktestResult(
        experiment_id="e",
        strategy_id="s",
        strategy_name="S",
        strategy_version="1",
        code_version="0.1.0",
        parameters={},
        data_source="synthetic",
        data_version="v1",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 10),
        initial_capital=100_000,
        cost_model="c",
        slippage_model="s",
        portfolio=port,
        signals=[],
        orders=[],
        rejected_orders=[],
        events=[],
    )


def test_drawdown_calculation():
    eq = np.array([100.0, 120.0, 90.0, 95.0])
    # peak 120, trough 90 → (90-120)/120 = -0.25
    assert _max_drawdown(eq) == pytest.approx(-0.25)


def test_zero_trades_metrics():
    points = [
        EquityPoint(datetime(2024, 1, 1), 100_000, 0, 100_000, 0, 0),
        EquityPoint(datetime(2024, 1, 2), 100_000, 0, 100_000, 0, 0),
    ]
    m = compute_metrics(_empty_result(points))
    assert m.number_of_trades == 0
    assert m.win_rate is None
    assert "zero_trades" in m.notes


def test_zero_volatility_sharpe_none():
    points = [
        EquityPoint(datetime(2024, 1, 1), 100_000, 0, 100_000, 0, 0),
        EquityPoint(datetime(2024, 1, 2), 100_000, 0, 100_000, 0, 0),
        EquityPoint(datetime(2024, 1, 3), 100_000, 0, 100_000, 0, 0),
    ]
    m = compute_metrics(_empty_result(points))
    assert m.annualized_volatility == 0.0
    assert m.sharpe_ratio is None
    assert "zero_volatility" in m.notes


def test_zero_drawdown_calmar_none():
    points = [
        EquityPoint(datetime(2024, 1, 1), 100_000, 0, 100_000, 0, 0),
        EquityPoint(datetime(2024, 1, 2), 101_000, 0, 101_000, 0, 0),
        EquityPoint(datetime(2024, 1, 3), 102_000, 0, 102_000, 0, 0),
    ]
    m = compute_metrics(_empty_result(points))
    assert m.maximum_drawdown == pytest.approx(0.0)
    assert m.calmar_ratio is None
    assert "zero_drawdown" in m.notes


def test_insufficient_history():
    m = compute_metrics(_empty_result([]))
    assert m.total_return is None
    assert "insufficient_history" in m.notes
