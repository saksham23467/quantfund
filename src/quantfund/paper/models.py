"""Phase 8 paper-trading core models (broker-independent)."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SessionMode(str, Enum):
    """Production paper vs infrastructure sandbox (demo/CI)."""

    PRODUCTION = "production"
    INFRASTRUCTURE_SANDBOX = "infrastructure_sandbox"


class PaperExecutionMode(str, Enum):
    NEXT_BAR_OPEN = "next_bar_open"


class PartialFillPolicy(str, Enum):
    ALL_OR_NOTHING = "all_or_nothing"
    ALLOW_PARTIAL = "allow_partial"


def deterministic_id(*parts: object) -> str:
    """Stable short hex id from stable inputs (paper path only)."""
    payload = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def state_hash(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class MarketDataEvent(BaseModel):
    """Immutable bar-oriented market event (RAW OHLC)."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    seq: int
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    instrument_id: str | None = None
    session_date: date | None = None
    source: str = "replay"

    @field_validator("open", "high", "low", "close")
    @classmethod
    def prices_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("prices must be positive")
        return float(v)

    @field_validator("volume")
    @classmethod
    def volume_non_neg(cls, v: float) -> float:
        if v < 0:
            raise ValueError("volume must be >= 0")
        return float(v)

    @field_validator("seq")
    @classmethod
    def seq_non_neg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("seq must be >= 0")
        return int(v)

    @model_validator(mode="after")
    def ohlc_ok(self) -> MarketDataEvent:
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be >= max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be <= min(open, close)")
        return self

    def resolved_session_date(self) -> date:
        return self.session_date or self.timestamp.date()


class PaperSessionConfig(BaseModel):
    """Immutable paper session configuration."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    mode: SessionMode = SessionMode.INFRASTRUCTURE_SANDBOX
    initial_cash: float = 100_000.0
    allow_negative_cash: bool = False
    execution_mode: PaperExecutionMode = PaperExecutionMode.NEXT_BAR_OPEN
    cost_model_id: str = "equity_delivery_v1"
    slippage_model_id: str = "fixed_bps_5"
    partial_fill_policy: PartialFillPolicy = PartialFillPolicy.ALL_OR_NOTHING
    partial_fill_ratio: float = 1.0  # used when ALLOW_PARTIAL
    stale_max_lag_events: int = 0  # 0 = only reject if timestamp < last watermark
    require_known_instruments: bool = False
    calendar_id: str = "NSE_EQ"
    strategy_id: str = "unknown"
    strategy_version: str = "0"
    dataset_id: str | None = None
    dataset_version: str | None = None
    certified_eligibility: str = "development_only"
    acceptance_evidence_id: str | None = None
    seed: str = "phase8"
    version: str = "paper_kernel_v1"
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("initial_cash")
    @classmethod
    def cash_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("initial_cash must be positive")
        return float(v)

    @field_validator("partial_fill_ratio")
    @classmethod
    def ratio_ok(cls, v: float) -> float:
        if v <= 0 or v > 1:
            raise ValueError("partial_fill_ratio must be in (0, 1]")
        return float(v)

    def config_hash(self) -> str:
        return state_hash(self.model_dump(mode="json"))
