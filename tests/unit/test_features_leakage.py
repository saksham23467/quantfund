"""Feature engine leakage and warmup tests."""

from __future__ import annotations

from datetime import datetime

from quantfund.data.models import MarketBar
from quantfund.features.engine import FeatureEngine


def _bars_with_future_spike() -> list[MarketBar]:
    bars = []
    price = 100.0
    for i, day in enumerate([2, 3, 4, 5, 8]):
        # Last bar spikes massively — must not affect asof before it
        close = 1000.0 if day == 8 else price + i
        bars.append(
            MarketBar(
                timestamp=datetime(2024, 1, day),
                symbol="TEST",
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=100,
            )
        )
    return bars


def test_asof_ignores_future_spike():
    bars = _bars_with_future_spike()
    engine = FeatureEngine()
    engine.configure([{"name": "sma", "window": 3}, {"name": "return_1"}])
    # asof Jan 5 must equal compute on bars<=Jan5
    clipped = [b for b in bars if b.timestamp <= datetime(2024, 1, 5)]
    full_asof = engine.asof(bars, datetime(2024, 1, 5), symbol="TEST")
    clipped_asof = engine.asof(clipped, datetime(2024, 1, 5), symbol="TEST")
    assert full_asof == clipped_asof
    # SMA at Jan5 uses closes 102,103,104 — not 1000
    assert full_asof["sma_3"] is not None
    assert full_asof["sma_3"] < 200


def test_feature_warmup_nan():
    bars = _bars_with_future_spike()
    engine = FeatureEngine()
    engine.configure([{"name": "sma", "window": 3}])
    frame = engine.compute(bars)
    # First two rows should be NaN/None for sma_3
    row0 = frame.asof(datetime(2024, 1, 2), symbol="TEST")
    assert row0.get("sma_3") is None
    row2 = frame.asof(datetime(2024, 1, 4), symbol="TEST")
    assert row2.get("sma_3") is not None


def test_asof_frame_no_future_rows():
    bars = _bars_with_future_spike()
    engine = FeatureEngine()
    engine.configure([{"name": "momentum", "window": 2}])
    frame = engine.compute(bars)
    vals = frame.asof(datetime(2024, 1, 4), symbol="TEST")
    # Ensure we didn't pick the spike bar
    assert datetime(2024, 1, 8) not in [
        b.timestamp for b in bars if b.close == vals.get("momentum_2")
    ]
