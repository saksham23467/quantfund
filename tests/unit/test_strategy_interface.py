"""Strategy metadata and interface tests."""

from __future__ import annotations

from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


def test_buy_and_hold_metadata():
    s = BuyAndHoldStrategy(symbol="TEST", allocation=0.95)
    meta = s.metadata()
    assert meta.strategy_id == "buy_and_hold"
    assert meta.strategy_version == "1.0.0"
    assert meta.parameters["symbol"] == "TEST"
    assert meta.code_version
