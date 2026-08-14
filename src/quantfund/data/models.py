"""Strongly typed market data models."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssetClass(str, Enum):
    """Asset class for future extensibility."""

    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    FUTURE = "future"
    OPTION = "option"


class SymbolHistoryEntry(BaseModel):
    """Historical symbol used by an instrument over a date interval."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    valid_from: date
    valid_to: date | None = None  # None = still current
    exchange: str | None = None


class Instrument(BaseModel):
    """Tradable or reference instrument metadata.

    Permanent identity is ``instrument_id`` (preferably ISIN-based), never
    today's ticker alone.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., min_length=1)
    instrument_id: str | None = None  # stable id, e.g. NSE:INE002A01018
    isin: str | None = None
    name: str | None = None
    exchange: str | None = None
    series: str | None = None  # e.g. EQ
    currency: str = "INR"
    asset_class: AssetClass = AssetClass.EQUITY
    listing_date: date | None = None
    delisting_date: date | None = None
    status: str = "active"  # active | delisted | suspended | merged | unknown
    terminal_event_id: str | None = None
    provider_symbol: str | None = None
    provider_symbols: dict[str, str] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    predecessor_instrument_id: str | None = None
    successor_instrument_id: str | None = None
    symbol_history: list[SymbolHistoryEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def strip_symbol(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("symbol must be non-empty")
        return cleaned

    @model_validator(mode="after")
    def default_instrument_id(self) -> Instrument:
        if self.instrument_id:
            return self
        if self.isin and self.exchange:
            object.__setattr__(self, "instrument_id", f"{self.exchange}:{self.isin}")
        elif self.exchange:
            object.__setattr__(self, "instrument_id", f"{self.exchange}:{self.symbol}")
        else:
            object.__setattr__(self, "instrument_id", f"UNKNOWN:{self.symbol}")
        return self

    def symbol_asof(self, on: date) -> str:
        """Resolve display symbol on date ``on`` via symbol_history if present."""
        if not self.symbol_history:
            return self.symbol
        for entry in sorted(self.symbol_history, key=lambda e: e.valid_from, reverse=True):
            if entry.valid_from <= on and (entry.valid_to is None or on <= entry.valid_to):
                return entry.symbol
        return self.symbol


class MarketBar(BaseModel):
    """OHLCV bar for a single instrument at a single timestamp."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    instrument_id: str | None = None

    @field_validator("open", "high", "low", "close")
    @classmethod
    def prices_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("prices must be positive")
        return float(value)

    @field_validator("volume")
    @classmethod
    def volume_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("volume must be >= 0")
        return float(value)

    @model_validator(mode="after")
    def validate_ohlc_relationships(self) -> MarketBar:
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be >= max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be <= min(open, close)")
        return self


class MarketEventType(str, Enum):
    """Event types emitted by the backtest engine."""

    BAR = "bar"


class MarketEvent(BaseModel):
    """Chronological market event consumed by the engine."""

    model_config = ConfigDict(frozen=True)

    event_type: MarketEventType = MarketEventType.BAR
    timestamp: datetime
    symbol: str
    bar: MarketBar
