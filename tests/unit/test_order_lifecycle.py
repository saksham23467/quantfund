"""Signal → Order → Fill lifecycle constraints."""

from __future__ import annotations

from datetime import datetime

from quantfund.backtest.broker_sim import BrokerSimulator, SlippageModel
from quantfund.backtest.costs import EquityDeliveryCostModel
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.trading.models import Fill, Order, OrderSide, OrderStatus, Signal, SignalAction


class _Tiny(Strategy):
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata("tiny", "Tiny", "1.0.0")

    def generate_signal(self, context: StrategyContext) -> Signal:
        return Signal(
            timestamp=context.timestamp,
            symbol=context.symbol,
            action=SignalAction.BUY,
            target_quantity=1,
        )


def test_strategy_produces_signal_and_order_not_fill(synthetic_bars):
    strat = _Tiny()
    bar = synthetic_bars[0]
    ctx = StrategyContext(
        timestamp=bar.timestamp,
        symbol=bar.symbol,
        history=[bar],
        position_quantity=0,
        cash=10_000,
    )
    signal = strat.generate_signal(ctx)
    orders = strat.generate_orders(signal, ctx)
    assert isinstance(signal, Signal)
    assert isinstance(orders[0], Order)
    assert not isinstance(orders[0], Fill)


def test_only_broker_creates_fill():
    order = Order(
        timestamp=datetime(2024, 1, 2),
        symbol="TEST",
        side=OrderSide.BUY,
        quantity=10,
        status=OrderStatus.ACCEPTED,
    )
    sim = BrokerSimulator(
        cost_model=EquityDeliveryCostModel(),
        slippage_model=SlippageModel(bps=0),
    )
    fill = sim.execute(order, execution_time=datetime(2024, 1, 3), open_price=100)
    assert isinstance(fill, Fill)
    assert fill.price == 100
    assert order.status == OrderStatus.FILLED
