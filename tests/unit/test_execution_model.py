"""Next-bar execution and look-ahead prevention tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from quantfund.backtest.broker_sim import SlippageModel
from quantfund.backtest.costs import EquityDeliveryCostConfig, EquityDeliveryCostModel
from quantfund.backtest.engine import BacktestConfig, BacktestEngine, LookAheadError
from quantfund.risk.limits import RiskConfig
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy
from quantfund.trading.models import Signal, SignalAction


class PeekingStrategy(Strategy):
    """Records max history timestamp seen; used to prove no future bars leak."""

    def __init__(self) -> None:
        self.max_seen: list[datetime] = []
        self.history_lens: list[int] = []

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata("peek", "Peek", "1.0.0")

    def generate_signal(self, context: StrategyContext) -> Signal:
        self.max_seen.append(max(b.timestamp for b in context.history))
        self.history_lens.append(len(context.history))
        # Attempting to use "future" would require bars beyond context — none exist.
        return Signal(
            timestamp=context.timestamp,
            symbol=context.symbol,
            action=SignalAction.HOLD,
        )


def _zero_cost_engine(strategy, capital=100_000.0):
    return BacktestEngine(
        strategy,
        config=BacktestConfig(
            initial_capital=capital,
            data_source="synthetic",
            data_version="m1",
            risk=RiskConfig(
                max_order_value=capital,
                max_position_value=capital,
                max_total_exposure=capital,
            ),
        ),
        cost_model=EquityDeliveryCostModel(
            EquityDeliveryCostConfig(
                brokerage_rate=0,
                stt_sell_rate=0,
                stt_buy_rate=0,
                exchange_rate=0,
                gst_rate=0,
                stamp_duty_buy_rate=0,
                stamp_duty_sell_rate=0,
                sebi_rate=0,
            )
        ),
        slippage_model=SlippageModel(bps=0),
    )


def test_next_bar_open_execution_not_same_bar(synthetic_bars):
    strategy = BuyAndHoldStrategy(symbol="TEST", allocation=0.95)
    engine = _zero_cost_engine(strategy)
    result = engine.run(synthetic_bars)

    assert len(result.portfolio.fills) == 1
    fill = result.portfolio.fills[0]
    # Signal on first bar close; fill on second bar open
    assert fill.timestamp == synthetic_bars[1].timestamp
    assert fill.price == pytest.approx(synthetic_bars[1].open)
    # Same-bar fill would have first bar timestamp — forbidden
    assert fill.timestamp != synthetic_bars[0].timestamp


def test_no_future_bars_in_strategy_context(synthetic_bars):
    strategy = PeekingStrategy()
    engine = _zero_cost_engine(strategy)
    engine.run(synthetic_bars)
    for i, ts in enumerate(strategy.max_seen):
        assert ts == synthetic_bars[i].timestamp
        assert strategy.history_lens[i] == i + 1


def test_same_bar_execution_flag_rejected():
    with pytest.raises(ValueError, match="same-bar"):
        BacktestEngine(
            BuyAndHoldStrategy(symbol="TEST"),
            config=BacktestConfig(allow_same_bar_execution=True),
        )


def test_unordered_bars_raise(synthetic_bars):
    bad = list(reversed(synthetic_bars))
    engine = _zero_cost_engine(BuyAndHoldStrategy(symbol="TEST"))
    with pytest.raises(LookAheadError):
        engine.run(bad)


def test_manual_expected_portfolio_buy_and_hold(synthetic_bars):
    """Hand-calculated expectation with zero costs/slippage."""
    capital = 100_000.0
    strategy = BuyAndHoldStrategy(symbol="TEST", allocation=0.95)
    engine = _zero_cost_engine(strategy, capital=capital)
    result = engine.run(synthetic_bars)

    # qty = int(100000 * 0.95 / first_close) = int(95000/102) = 931
    first_close = synthetic_bars[0].close
    qty = int((capital * 0.95) // first_close)
    assert qty == 931

    fill_price = synthetic_bars[1].open  # 102
    cash_after = capital - qty * fill_price
    final_mark = synthetic_bars[-1].close  # 114
    expected_equity = cash_after + qty * final_mark

    assert result.portfolio.fills[0].quantity == qty
    assert result.portfolio.cash == pytest.approx(cash_after)
    assert result.final_equity == pytest.approx(expected_equity)
