"""End-to-end smoke integration test on SYNTHETIC data with costs + slippage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantfund.analytics.metrics import compute_metrics
from quantfund.analytics.report import write_reports
from quantfund.backtest.broker_sim import SlippageModel
from quantfund.backtest.costs import EquityDeliveryCostConfig, EquityDeliveryCostModel
from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.risk.limits import RiskConfig
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


def test_full_smoke_with_costs_and_report(synthetic_bars, tmp_path: Path):
    capital = 100_000.0
    strategy = BuyAndHoldStrategy(symbol="TEST", allocation=0.95)
    cost_cfg = EquityDeliveryCostConfig()
    engine = BacktestEngine(
        strategy,
        config=BacktestConfig(
            experiment_id="integration_smoke",
            initial_capital=capital,
            data_source="synthetic_fixture",
            data_version="m1_v1",
            start_date=synthetic_bars[0].timestamp,
            end_date=synthetic_bars[-1].timestamp,
            risk=RiskConfig(
                max_order_value=capital,
                max_position_value=capital,
                max_total_exposure=capital,
            ),
        ),
        cost_model=EquityDeliveryCostModel(cost_cfg),
        slippage_model=SlippageModel(bps=5.0),
    )
    result = engine.run(synthetic_bars)
    metrics = compute_metrics(result)

    assert metrics.number_of_trades == 1
    assert result.portfolio.total_transaction_costs > 0
    assert result.portfolio.total_slippage > 0
    assert result.final_equity != capital

    # Fill at next open with 5 bps slippage
    open_px = synthetic_bars[1].open
    expected_fill = open_px * (1 + 5.0 / 10_000.0)
    assert result.portfolio.fills[0].price == pytest.approx(expected_fill)

    json_path, text_path = write_reports(result, tmp_path)
    assert json_path.exists()
    assert text_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["experiment_id"] == "integration_smoke"
    assert payload["strategy_id"] == "buy_and_hold"
    assert payload["metrics"]["number_of_trades"] == 1
    assert payload["initial_capital"] == capital
