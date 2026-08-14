"""Shared pytest fixtures. Synthetic data is explicitly labeled SYNTHETIC."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from quantfund.data.models import MarketBar
from quantfund.data.normalize import dataframe_to_bars
from quantfund.data.validate import validate_bars

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def synthetic_bars() -> list[MarketBar]:
    """Tiny deterministic SYNTHETIC OHLCV series for manual expectation checks."""
    df = pd.read_csv(FIXTURES / "synthetic_bars.csv", parse_dates=["timestamp"])
    bars = dataframe_to_bars(df, symbol="TEST")
    return validate_bars(bars)


@pytest.fixture
def make_bar():
    def _make(
        day: str,
        o: float,
        h: float,
        l: float,
        c: float,
        v: float = 1000.0,
        symbol: str = "TEST",
    ) -> MarketBar:
        return MarketBar(
            timestamp=datetime.fromisoformat(day),
            symbol=symbol,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=v,
        )

    return _make
