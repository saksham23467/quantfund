"""Phase 15 decision models — WOULD_* only; REAL_ORDER impossible."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OrderReality(str, Enum):
    WOULD_ORDER = "WOULD_ORDER"
    SIMULATED_ORDER = "SIMULATED_ORDER"
    REAL_ORDER = "REAL_ORDER"  # must never be emitted in Phase 15


class SessionState(str, Enum):
    CREATED = "CREATED"
    PREFLIGHT = "PREFLIGHT"
    CONNECTED = "CONNECTED"
    WARMING_UP = "WARMING_UP"
    RUNNING_SHADOW = "RUNNING_SHADOW"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    FAILED_SAFE = "FAILED_SAFE"
    SESSION_INVALIDATED = "SESSION_INVALIDATED"


@dataclass(frozen=True)
class WouldOrder:
    decision_id: str
    strategy_id: str
    instrument_id: str
    side: str
    quantity: float
    intended_price: float
    timestamp: datetime
    reason: str
    risk_result: str
    market_data_version: str
    strategy_hash: str
    reality: OrderReality = OrderReality.WOULD_ORDER
    symbol: str = ""
    exec_seq: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.reality is OrderReality.REAL_ORDER:
            raise ValueError("phase15_real_order_forbidden")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reality.value,
            "decision_id": self.decision_id,
            "strategy_id": self.strategy_id,
            "instrument_id": self.instrument_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "intended_price": self.intended_price,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "risk_result": self.risk_result,
            "market_data_version": self.market_data_version,
            "strategy_hash": self.strategy_hash,
            "exec_seq": self.exec_seq,
            "extras": dict(self.extras),
        }


FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "access_token",
        "request_token",
        "password",
        "secret",
        "authorization",
        "zerodha_api_key",
        "zerodha_access_token",
        "signing_key",
    }
)


def scrub_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    """Redact credential-like keys recursively (not freeze_token / hashes)."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        lk = str(k).lower()
        is_secret = lk in FORBIDDEN_SECRET_KEYS or any(
            s in lk
            for s in (
                "api_key",
                "api_secret",
                "access_token",
                "request_token",
                "password",
                "authorization",
                "signing_key",
                "client_secret",
            )
        )
        if is_secret:
            out[k] = "***REDACTED***"
        elif isinstance(v, dict):
            out[k] = scrub_secrets(v)
        else:
            out[k] = v
    return out
