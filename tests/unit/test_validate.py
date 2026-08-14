"""Duplicate timestamp and chronological ordering tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from quantfund.data.models import MarketBar
from quantfund.data.validate import ValidationError, validate_bars


def _bar(ts: str, symbol: str = "A") -> MarketBar:
    return MarketBar(
        timestamp=datetime.fromisoformat(ts),
        symbol=symbol,
        open=10,
        high=11,
        low=9,
        close=10.5,
        volume=1,
    )


def test_duplicate_timestamps_rejected():
    bars = [_bar("2024-01-01"), _bar("2024-01-01")]
    with pytest.raises(ValidationError, match="duplicate"):
        validate_bars(bars)


def test_out_of_order_timestamps_rejected():
    bars = [_bar("2024-01-02"), _bar("2024-01-01")]
    with pytest.raises(ValidationError, match="not ordered"):
        validate_bars(bars)


def test_ordered_unique_ok():
    bars = [_bar("2024-01-01"), _bar("2024-01-02")]
    assert validate_bars(bars) == bars


def test_empty_rejected_by_default():
    with pytest.raises(ValidationError):
        validate_bars([])


def test_same_timestamp_different_symbols_ok():
    bars = [_bar("2024-01-01", "A"), _bar("2024-01-01", "B")]
    assert len(validate_bars(bars)) == 2
