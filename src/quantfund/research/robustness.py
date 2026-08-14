"""Robustness suite: cost/slippage/parameter sensitivity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from quantfund.backtest.broker_sim import SlippageModel
from quantfund.backtest.costs import EquityDeliveryCostConfig, EquityDeliveryCostModel
from quantfund.backtest.engine import BacktestConfig, BacktestEngine, BacktestResult
from quantfund.data.models import MarketBar
from quantfund.strategies.base import Strategy


@dataclass
class RobustnessCase:
    name: str
    result_metrics: dict[str, Any]
    passed: bool
    detail: str


def _scale_cost_model(scale: float) -> EquityDeliveryCostModel:
    base = EquityDeliveryCostConfig()
    return EquityDeliveryCostModel(
        EquityDeliveryCostConfig(
            brokerage_rate=base.brokerage_rate * scale,
            stt_sell_rate=base.stt_sell_rate * scale,
            stt_buy_rate=base.stt_buy_rate * scale,
            exchange_rate=base.exchange_rate * scale,
            gst_rate=base.gst_rate,
            stamp_duty_buy_rate=base.stamp_duty_buy_rate * scale,
            stamp_duty_sell_rate=base.stamp_duty_sell_rate * scale,
            sebi_rate=base.sebi_rate * scale,
        )
    )


def run_robustness_suite(
    *,
    strategy_factory: Callable[[], Strategy],
    bars: list[MarketBar],
    base_config: BacktestConfig,
    baseline_total_return: float | None,
    context_enricher=None,
    cost_scales: list[float] | None = None,
    slippage_bps_list: list[float] | None = None,
) -> dict[str, Any]:
    """Run sensitivity cases; mark fragile if sign flips vs baseline under 2x costs."""
    from quantfund.analytics.metrics import compute_metrics

    cost_scales = cost_scales or [0.5, 1.0, 2.0, 3.0]
    slippage_bps_list = slippage_bps_list or [0.0, 5.0, 10.0, 20.0]
    cases: list[RobustnessCase] = []

    for scale in cost_scales:
        engine = BacktestEngine(
            strategy_factory(),
            config=base_config,
            cost_model=_scale_cost_model(scale),
            slippage_model=SlippageModel(bps=5.0),
            context_enricher=context_enricher,
        )
        result = engine.run(bars)
        metrics = compute_metrics(result)
        tr = metrics.total_return
        passed = True
        detail = f"cost_scale={scale}, total_return={tr}"
        if (
            scale >= 2.0
            and baseline_total_return is not None
            and tr is not None
            and baseline_total_return > 0
            and tr < 0
        ):
            passed = False
            detail += " (sign flip under elevated costs)"
        cases.append(RobustnessCase(f"cost_x{scale}", metrics.__dict__, passed, detail))

    for bps in slippage_bps_list:
        engine = BacktestEngine(
            strategy_factory(),
            config=base_config,
            cost_model=EquityDeliveryCostModel(),
            slippage_model=SlippageModel(bps=bps),
            context_enricher=context_enricher,
        )
        result = engine.run(bars)
        metrics = compute_metrics(result)
        cases.append(
            RobustnessCase(
                f"slippage_{bps}bps",
                metrics.__dict__,
                True,
                f"slippage_bps={bps}, total_return={metrics.total_return}",
            )
        )

    pass_rate = sum(1 for c in cases if c.passed) / len(cases) if cases else 0.0
    fragile = any(not c.passed for c in cases)
    return {
        "cases": [
            {
                "name": c.name,
                "passed": c.passed,
                "detail": c.detail,
                "total_return": c.result_metrics.get("total_return"),
                "sharpe_ratio": c.result_metrics.get("sharpe_ratio"),
            }
            for c in cases
        ],
        "pass_rate": pass_rate,
        "fragile": fragile,
    }
