"""DataProvider interface contract tests (no network)."""

from __future__ import annotations

from datetime import datetime

from quantfund.data.models import Instrument, MarketBar
from quantfund.data.providers.base import DataProvider


class FakeProvider(DataProvider):
    def __init__(self, bars: list[MarketBar]) -> None:
        self._bars = bars

    @property
    def name(self) -> str:
        return "fake"

    def get_instruments(self) -> list[Instrument]:
        symbols = sorted({b.symbol for b in self._bars})
        return [Instrument(symbol=s) for s in symbols]

    def get_history(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[MarketBar]:
        out = [b for b in self._bars if b.symbol == symbol]
        if start:
            out = [b for b in out if b.timestamp >= start]
        if end:
            out = [b for b in out if b.timestamp <= end]
        return out


def test_provider_interface(synthetic_bars):
    provider: DataProvider = FakeProvider(synthetic_bars)
    assert provider.name == "fake"
    assert provider.get_instruments()[0].symbol == "TEST"
    hist = provider.get_history("TEST")
    assert len(hist) == 5
    assert hist[0].timestamp < hist[-1].timestamp
