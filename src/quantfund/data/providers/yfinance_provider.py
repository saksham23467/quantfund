"""yfinance-backed DataProvider for development prototyping only.

source_grade = non_exchange. Datasets derived solely from this provider must be
labeled development / research_eligibility=development_only and must NOT be
treated as production-grade research data.

Not suitable as an exchange-grade India market data source. Corporate actions,
survivorship, and NSE/BSE nuances may be incomplete or incorrect.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from quantfund.data.grades import SourceGrade
from quantfund.data.models import AssetClass, Instrument, MarketBar
from quantfund.data.normalize import dataframe_to_bars
from quantfund.data.providers.capabilities import ProviderCapabilities, yfinance_capabilities
from quantfund.data.providers.roles import DevelopmentProvider
from quantfund.data.validate import validate_bars


class YFinanceProvider(DevelopmentProvider):
    """Development-only historical data via Yahoo Finance.

    source_grade is always non_exchange and can never become research_eligible
    merely because bars pass schema validation.
    """

    def __init__(
        self,
        instruments: list[Instrument] | None = None,
        *,
        raw_dir: Path | None = None,
        save_raw: bool = True,
    ) -> None:
        self._instruments = list(instruments or [])
        self._raw_dir = raw_dir
        self._save_raw = save_raw
        self._by_symbol = {i.symbol: i for i in self._instruments}

    @property
    def name(self) -> str:
        return "yfinance"

    @property
    def source_grade(self) -> SourceGrade:
        return SourceGrade.NON_EXCHANGE

    def capabilities(self) -> ProviderCapabilities:
        return yfinance_capabilities()

    def get_instruments(self) -> list[Instrument]:
        return list(self._instruments)

    def register(self, instrument: Instrument) -> None:
        """Register an instrument mapping for subsequent history fetches."""
        self._instruments.append(instrument)
        self._by_symbol[instrument.symbol] = instrument

    def get_history(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[MarketBar]:
        instrument = self._by_symbol.get(symbol)
        yahoo_symbol = instrument.provider_symbol if instrument else symbol
        if instrument is None:
            # Allow ad-hoc fetch while still recording a minimal instrument.
            instrument = Instrument(
                symbol=symbol,
                provider_symbol=yahoo_symbol,
                asset_class=AssetClass.EQUITY,
            )
            self.register(instrument)
            yahoo_symbol = instrument.provider_symbol or symbol

        ticker = yf.Ticker(yahoo_symbol)
        kwargs: dict = {"auto_adjust": False, "actions": False}
        if start is not None:
            kwargs["start"] = start.strftime("%Y-%m-%d")
        if end is not None:
            kwargs["end"] = end.strftime("%Y-%m-%d")
        if start is None and end is None:
            kwargs["period"] = "1y"

        raw = ticker.history(**kwargs)
        if raw is None or raw.empty:
            return []

        if self._save_raw and self._raw_dir is not None:
            self._raw_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            out = self._raw_dir / f"yfinance_{symbol}_{stamp}.csv"
            raw.to_csv(out)

        frame = raw.reset_index()
        # yfinance may return Date or Datetime as index name.
        bars = dataframe_to_bars(frame, symbol=symbol)
        return validate_bars(bars, require_non_empty=False)


def default_india_equity(symbol: str, yahoo_symbol: str, name: str | None = None) -> Instrument:
    """Helper for NSE-listed equities via Yahoo ``.NS`` suffix."""
    return Instrument(
        symbol=symbol,
        name=name,
        exchange="NSE",
        currency="INR",
        asset_class=AssetClass.EQUITY,
        provider_symbol=yahoo_symbol,
    )
