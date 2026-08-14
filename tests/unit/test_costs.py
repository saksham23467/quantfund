"""Transaction cost model tests."""

from __future__ import annotations

import pytest

from quantfund.backtest.costs import (
    EquityDeliveryCostConfig,
    EquityDeliveryCostModel,
    MarketSegment,
)
from quantfund.trading.models import OrderSide


def test_buy_costs_itemized():
    model = EquityDeliveryCostModel(
        EquityDeliveryCostConfig(
            brokerage_rate=0.001,
            brokerage_min=0,
            stt_buy_rate=0.0,
            stt_sell_rate=0.001,
            exchange_rate=0.0001,
            gst_rate=0.18,
            stamp_duty_buy_rate=0.00015,
            stamp_duty_sell_rate=0.0,
            sebi_rate=0.000001,
        )
    )
    # turnover = 100 * 10 = 1000
    c = model.compute(side=OrderSide.BUY, quantity=10, price=100)
    assert c.brokerage == pytest.approx(1.0)
    assert c.exchange_charges == pytest.approx(0.1)
    assert c.gst == pytest.approx((1.0 + 0.1) * 0.18)
    assert c.stamp_duty == pytest.approx(0.15)
    assert c.stt == 0.0
    assert c.sebi_charges == pytest.approx(0.001)
    assert c.total == pytest.approx(
        c.brokerage + c.stt + c.exchange_charges + c.gst + c.stamp_duty + c.sebi_charges
    )


def test_sell_applies_stt_assumption():
    model = EquityDeliveryCostModel(
        EquityDeliveryCostConfig(stt_sell_rate=0.001, stt_buy_rate=0.0)
    )
    c = model.compute(side=OrderSide.SELL, quantity=10, price=100)
    assert c.stt == pytest.approx(1.0)


def test_futures_segment_not_implemented():
    model = EquityDeliveryCostModel()
    with pytest.raises(NotImplementedError):
        model.compute(
            side=OrderSide.BUY,
            quantity=1,
            price=100,
            segment=MarketSegment.FUTURES,
        )
