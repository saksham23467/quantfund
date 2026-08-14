"""Slippage, portfolio accounting, and P&L tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from quantfund.backtest.broker_sim import BrokerSimulator, SlippageModel
from quantfund.backtest.costs import EquityDeliveryCostConfig, EquityDeliveryCostModel
from quantfund.backtest.portfolio import Portfolio
from quantfund.trading.models import Fill, Order, OrderSide, OrderStatus


def test_buy_slippage_increases_price():
    sim = BrokerSimulator(
        cost_model=EquityDeliveryCostModel(
            EquityDeliveryCostConfig(
                brokerage_rate=0,
                stt_sell_rate=0,
                exchange_rate=0,
                gst_rate=0,
                stamp_duty_buy_rate=0,
                sebi_rate=0,
            )
        ),
        slippage_model=SlippageModel(bps=100),  # 1%
    )
    order = Order(
        timestamp=datetime(2024, 1, 1),
        symbol="T",
        side=OrderSide.BUY,
        quantity=1,
        status=OrderStatus.ACCEPTED,
    )
    fill = sim.execute(order, execution_time=datetime(2024, 1, 2), open_price=100)
    assert fill.price == pytest.approx(101.0)
    assert fill.slippage_per_unit == pytest.approx(1.0)


def test_sell_slippage_decreases_price():
    sim = BrokerSimulator(
        cost_model=EquityDeliveryCostModel(
            EquityDeliveryCostConfig(
                brokerage_rate=0,
                stt_sell_rate=0,
                exchange_rate=0,
                gst_rate=0,
                stamp_duty_buy_rate=0,
                stamp_duty_sell_rate=0,
                sebi_rate=0,
            )
        ),
        slippage_model=SlippageModel(bps=100),
    )
    order = Order(
        timestamp=datetime(2024, 1, 1),
        symbol="T",
        side=OrderSide.SELL,
        quantity=1,
        status=OrderStatus.ACCEPTED,
    )
    fill = sim.execute(order, execution_time=datetime(2024, 1, 2), open_price=100)
    assert fill.price == pytest.approx(99.0)


def test_portfolio_buy_sell_pnl():
    port = Portfolio(cash=10_000)
    buy = Fill(
        order_id="1",
        timestamp=datetime(2024, 1, 2),
        symbol="T",
        side=OrderSide.BUY,
        quantity=10,
        price=100,
        slippage_per_unit=0,
        transaction_cost=5,
        gross_value=1000,
        net_cash_delta=-(1000 + 5),
    )
    port.apply_fill(buy)
    assert port.cash == pytest.approx(8995)
    assert port.position_quantity("T") == 10
    assert port.positions["T"].average_entry_price == 100

    sell = Fill(
        order_id="2",
        timestamp=datetime(2024, 1, 3),
        symbol="T",
        side=OrderSide.SELL,
        quantity=10,
        price=110,
        slippage_per_unit=0,
        transaction_cost=7,
        gross_value=1100,
        net_cash_delta=1100 - 7,
    )
    port.apply_fill(sell)
    assert port.position_quantity("T") == 0
    assert port.realized_pnl == pytest.approx(100.0)  # (110-100)*10
    assert port.cash == pytest.approx(8995 + 1093)


def test_short_selling_rejected_by_portfolio():
    port = Portfolio(cash=1000)
    with pytest.raises(ValueError, match="short"):
        port.apply_fill(
            Fill(
                order_id="x",
                timestamp=datetime(2024, 1, 1),
                symbol="T",
                side=OrderSide.SELL,
                quantity=1,
                price=10,
                slippage_per_unit=0,
                transaction_cost=0,
                gross_value=10,
                net_cash_delta=10,
            )
        )
