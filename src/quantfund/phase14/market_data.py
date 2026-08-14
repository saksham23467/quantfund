"""Provider-neutral real-time market data — yfinance remains simulation-only."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from quantfund.data.models import MarketBar
from quantfund.paper.models import MarketDataEvent, deterministic_id
from quantfund.phase12.market_data import to_ist
from quantfund.phase13.replay import make_yfinance_labeled_fixture


@dataclass(frozen=True)
class RealTimeBar:
    """Incoming bar/tick with freshness metadata."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    received_at: datetime
    sequence: int
    instrument_id: str | None = None

    @property
    def data_age_seconds(self) -> float:
        return max(
            0.0,
            (self.received_at - self.timestamp.astimezone(self.received_at.tzinfo)).total_seconds()
            if self.timestamp.tzinfo
            else (self.received_at - self.timestamp.replace(tzinfo=timezone.utc)).total_seconds(),
        )

    def is_stale(self, max_age_seconds: float | None) -> bool:
        if max_age_seconds is None:
            return False
        return self.data_age_seconds > max_age_seconds

    def to_market_bar(self) -> MarketBar:
        return MarketBar(
            timestamp=self.timestamp,
            symbol=self.symbol,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            instrument_id=self.instrument_id,
        )

    def to_event(self, *, session_prefix: str = "p14") -> MarketDataEvent:
        return MarketDataEvent(
            event_id=deterministic_id(
                session_prefix, self.symbol, self.sequence, self.timestamp.isoformat()
            ),
            seq=self.sequence,
            timestamp=self.timestamp,
            symbol=self.symbol,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            instrument_id=self.instrument_id,
            session_date=self.timestamp.date(),
            source=self.source,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
            "received_at": self.received_at.isoformat(),
            "sequence": self.sequence,
            "data_age_seconds": self.data_age_seconds,
        }


@dataclass
class ProviderHealth:
    connected: bool
    last_update: datetime | None
    subscribed: tuple[str, ...]
    source_grade: str = "non_exchange"
    research_eligible: bool = False
    simulation_only: bool = True
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "subscribed": list(self.subscribed),
            "source_grade": self.source_grade,
            "research_eligible": self.research_eligible,
            "simulation_only": self.simulation_only,
            "detail": self.detail,
        }


class RealTimeMarketDataProvider(ABC):
    """Provider-neutral real-time / polled market data interface."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def subscribe(self, symbols: list[str]) -> None: ...

    @abstractmethod
    def next_bar(self) -> RealTimeBar | None: ...

    @abstractmethod
    def health(self) -> ProviderHealth: ...

    @abstractmethod
    def last_update(self) -> datetime | None: ...


class YFinanceSimulationMarketDataProvider(RealTimeMarketDataProvider):
    """Polling/simulation source labeled yfinance — never research-grade.

    Demo/CI: feed a deterministic bar list. Optional network poll is still
    DEVELOPMENT_ONLY / non_exchange and fail-closed on errors.
    """

    SOURCE_GRADE = "non_exchange"
    RESEARCH_ELIGIBLE = False
    SIMULATION_ONLY = True

    def __init__(
        self,
        *,
        stream: list[RealTimeBar] | None = None,
        max_staleness_seconds: float | None = None,
    ) -> None:
        self._stream = list(stream or [])
        self._idx = 0
        self._symbols: list[str] = []
        self._connected = False
        self._last_update: datetime | None = None
        self.max_staleness_seconds = max_staleness_seconds

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def subscribe(self, symbols: list[str]) -> None:
        self._symbols = list(symbols)

    def next_bar(self) -> RealTimeBar | None:
        if not self._connected:
            return None
        while self._idx < len(self._stream):
            bar = self._stream[self._idx]
            self._idx += 1
            if self._symbols and bar.symbol not in self._symbols:
                continue
            self._last_update = bar.received_at
            return bar
        return None

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            connected=self._connected,
            last_update=self._last_update,
            subscribed=tuple(self._symbols),
            source_grade=self.SOURCE_GRADE,
            research_eligible=self.RESEARCH_ELIGIBLE,
            simulation_only=self.SIMULATION_ONLY,
            detail="yfinance_simulation_polling_source",
        )

    def last_update(self) -> datetime | None:
        return self._last_update

    @classmethod
    def from_fixture_bars(
        cls,
        *,
        symbol: str = "RELIANCE",
        n: int = 12,
        received_lag_seconds: float = 0.0,
        max_staleness_seconds: float | None = None,
        force_stale_from_seq: int | None = None,
        stale_lag_seconds: float = 10_000.0,
    ) -> YFinanceSimulationMarketDataProvider:
        """Deterministic simulated real-time stream (market need not be open)."""
        bars = make_yfinance_labeled_fixture(symbol=symbol, n=n)
        stream: list[RealTimeBar] = []
        for i, b in enumerate(bars):
            ts = to_ist(b.timestamp)
            lag = stale_lag_seconds if (
                force_stale_from_seq is not None and i >= force_stale_from_seq
            ) else received_lag_seconds
            received = datetime.fromtimestamp(
                ts.timestamp() + lag, tz=timezone.utc
            )
            stream.append(
                RealTimeBar(
                    symbol=b.symbol,
                    timestamp=ts,
                    open=float(b.open),
                    high=float(b.high),
                    low=float(b.low),
                    close=float(b.close),
                    volume=float(b.volume or 0),
                    source="yfinance_public_development",
                    received_at=received,
                    sequence=i,
                    instrument_id=b.instrument_id or f"NSE:{b.symbol}",
                )
            )
        return cls(stream=stream, max_staleness_seconds=max_staleness_seconds)
