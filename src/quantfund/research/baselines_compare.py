"""Baseline comparisons: buy-and-hold and cash."""

from __future__ import annotations

from typing import Any

from quantfund.analytics.metrics import compute_metrics
from quantfund.backtest.broker_sim import SlippageModel
from quantfund.backtest.costs import EquityDeliveryCostModel
from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.data.models import MarketBar
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


def run_buy_and_hold_baseline(
    bars: list[MarketBar],
    *,
    symbol: str,
    config: BacktestConfig,
) -> dict[str, Any]:
    engine = BacktestEngine(
        BuyAndHoldStrategy(symbol=symbol, allocation=0.95),
        config=config,
        cost_model=EquityDeliveryCostModel(),
        slippage_model=SlippageModel(bps=5.0),
    )
    result = engine.run(bars)
    metrics = compute_metrics(result)
    return {
        "strategy_id": "buy_and_hold",
        "final_equity": result.final_equity,
        "metrics": metrics.__dict__,
    }


def cash_baseline(initial_capital: float) -> dict[str, Any]:
    return {
        "strategy_id": "cash",
        "final_equity": initial_capital,
        "metrics": {
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "maximum_drawdown": 0.0,
            "cagr": 0.0,
        },
    }
