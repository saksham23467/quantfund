"""DEVELOPMENT_DATA provider identity — never research/exchange-authoritative."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from quantfund.data.development.config import (
    DATA_CLASS_DEVELOPMENT,
    EXCHANGE_AUTHORITY,
    PROVIDER_ID,
    RESEARCH_GRADE,
    SOURCE_GRADE,
)
from quantfund.data.development.normalize import load_bars_directory, load_ohlcv_csv
from quantfund.data.grades import SourceGrade
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.providers.base import DataProvider


class DevelopmentDataProvider(DataProvider):
    """Free/public Indian equity development data (engineering only)."""

    def __init__(
        self,
        *,
        bars: list[MarketBar] | None = None,
        source_label: str = PROVIDER_ID,
        synthetic: bool = False,
    ) -> None:
        self._bars = list(bars or [])
        self._by_symbol: dict[str, list[MarketBar]] = {}
        for b in self._bars:
            self._by_symbol.setdefault(b.symbol, []).append(b)
        self._source_label = source_label
        self._synthetic = synthetic

    @property
    def name(self) -> str:
        return PROVIDER_ID

    @property
    def data_class(self) -> str:
        return DATA_CLASS_DEVELOPMENT

    @property
    def source_grade(self) -> str:
        return SOURCE_GRADE

    @property
    def research_grade(self) -> bool:
        return RESEARCH_GRADE

    @property
    def exchange_authority(self) -> bool:
        return EXCHANGE_AUTHORITY

    @property
    def synthetic(self) -> bool:
        return self._synthetic

    def get_history(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[MarketBar]:
        sym = symbol.replace(".NS", "").replace(".NSE", "")
        bars = list(self._by_symbol.get(sym, []))
        if start is not None:
            bars = [b for b in bars if b.timestamp >= start]
        if end is not None:
            bars = [b for b in bars if b.timestamp <= end]
        return bars

    def get_instruments(self) -> list[Instrument]:
        from quantfund.data.development.normalize import instruments_from_bars

        return instruments_from_bars(self._bars)

    def attestation(self) -> dict:
        return {
            "provider_id": PROVIDER_ID,
            "data_class": DATA_CLASS_DEVELOPMENT,
            "source_grade": SOURCE_GRADE,
            "research_grade": False,
            "exchange_authority": False,
            "synthetic": self._synthetic,
            "source_label": self._source_label,
            # Maps to non_exchange for any code path expecting SourceGrade enum
            "source_grade_enum_equivalent": SourceGrade.NON_EXCHANGE.value,
        }

    @classmethod
    def from_file(cls, path: Path) -> DevelopmentDataProvider:
        path = Path(path)
        if path.is_dir():
            bars = load_bars_directory(path)
            label = f"offline_dir:{path.name}"
        elif path.is_file():
            bars = load_ohlcv_csv(path)
            label = f"offline_file:{path.name}"
        else:
            raise FileNotFoundError(path)
        return cls(bars=bars, source_label=label, synthetic=False)

    @classmethod
    def from_yfinance_fetch(
        cls,
        symbols: list[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> DevelopmentDataProvider:
        """Optional network fetch via existing YFinanceProvider — still DEVELOPMENT_DATA."""
        from quantfund.data.providers.yfinance_provider import YFinanceProvider

        from quantfund.data.providers.yfinance_provider import default_india_equity

        instruments = []
        for sym in symbols:
            clean = sym.replace(".NS", "").replace(".NSE", "")
            yahoo = sym if sym.endswith(".NS") else f"{clean}.NS"
            instruments.append(default_india_equity(clean, yahoo))
        yf = YFinanceProvider(instruments, save_raw=False)
        bars: list[MarketBar] = []
        for inst in instruments:
            bars.extend(yf.get_history(inst.symbol, start=start, end=end))
        return cls(
            bars=bars,
            source_label="yfinance_public_development",
            synthetic=False,
        )
