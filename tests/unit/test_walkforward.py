"""Walk-forward window ordering tests."""

from __future__ import annotations

from datetime import datetime

from quantfund.data.models import MarketBar
from quantfund.research.walkforward import WalkForwardConfig, generate_walkforward_windows


def test_walkforward_no_backward_leak():
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, d),
            symbol="TEST",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        )
        for d in range(1, 16)
    ]
    windows = generate_walkforward_windows(
        bars,
        WalkForwardConfig(
            train_sessions=3,
            validation_sessions=1,
            test_sessions=1,
            step_sessions=1,
            mode="rolling",
        ),
    )
    assert windows
    for w in windows:
        assert w.train.end < w.validation.start
        assert w.validation.end < w.test.start
        # Later absolute dates not in earlier train
        train_dates = {b.timestamp.date() for b in w.train_bars}
        assert w.test.start not in train_dates
