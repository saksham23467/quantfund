"""Independent risk limit tests."""

from __future__ import annotations

from datetime import datetime

from quantfund.risk.limits import RiskConfig, RiskEngine
from quantfund.trading.models import Order, OrderSide


def _order(qty: float = 10) -> Order:
    return Order(
        timestamp=datetime(2024, 1, 1),
        symbol="T",
        side=OrderSide.BUY,
        quantity=qty,
    )


def test_max_order_value_rejects():
    engine = RiskEngine(RiskConfig(max_order_value=500, max_position_value=1e9, max_total_exposure=1e9))
    decision = engine.check_order(_order(10), ref_price=100, current_position_qty=0, current_exposure=0)
    assert not decision.accepted
    assert decision.reason == "max_order_value"


def test_max_position_value_rejects():
    engine = RiskEngine(RiskConfig(max_order_value=1e9, max_position_value=500, max_total_exposure=1e9))
    decision = engine.check_order(_order(10), ref_price=100, current_position_qty=0, current_exposure=0)
    assert not decision.accepted
    assert decision.reason == "max_position_value"


def test_max_total_exposure_rejects():
    engine = RiskEngine(RiskConfig(max_order_value=1e9, max_position_value=1e9, max_total_exposure=500))
    decision = engine.check_order(_order(10), ref_price=100, current_position_qty=0, current_exposure=0)
    assert not decision.accepted
    assert decision.reason == "max_total_exposure"


def test_kill_switch():
    engine = RiskEngine(RiskConfig(kill_switch=True))
    decision = engine.check_order(_order(1), ref_price=10, current_position_qty=0, current_exposure=0)
    assert not decision.accepted
    assert decision.reason == "kill_switch"


def test_short_sell_rejected():
    engine = RiskEngine(RiskConfig())
    sell = Order(
        timestamp=datetime(2024, 1, 1),
        symbol="T",
        side=OrderSide.SELL,
        quantity=5,
    )
    decision = engine.check_order(sell, ref_price=10, current_position_qty=2, current_exposure=20)
    assert not decision.accepted
    assert decision.reason == "shorting_not_allowed"
