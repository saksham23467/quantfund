"""OHLC and instrument model validation tests."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from quantfund.data.models import Instrument, MarketBar


def test_valid_bar():
    bar = MarketBar(
        timestamp=datetime(2024, 1, 2),
        symbol="TEST",
        open=100,
        high=105,
        low=99,
        close=102,
        volume=10,
    )
    assert bar.close == 102


def test_high_must_be_ge_max_open_close():
    with pytest.raises(ValidationError):
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=100,
            high=100.5,
            low=99,
            close=102,
            volume=1,
        )


def test_low_must_be_le_min_open_close():
    with pytest.raises(ValidationError):
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=100,
            high=105,
            low=101,
            close=99,
            volume=1,
        )


def test_high_ge_low():
    with pytest.raises(ValidationError):
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=100,
            high=98,
            low=99,
            close=100,
            volume=1,
        )


def test_prices_must_be_positive():
    with pytest.raises(ValidationError):
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=0,
            high=1,
            low=0.5,
            close=1,
            volume=1,
        )


def test_volume_non_negative():
    with pytest.raises(ValidationError):
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=-1,
        )


def test_instrument_symbol_required():
    with pytest.raises(ValidationError):
        Instrument(symbol="  ")
