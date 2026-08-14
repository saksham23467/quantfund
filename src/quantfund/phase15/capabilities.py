"""Capability models — write capabilities must be FALSE in Phase 15."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketDataCapabilities:
    provider_id: str
    source_grade: str
    exchange: str
    timezone: str
    timestamp_semantics: str
    realtime_quotes: bool
    historical_bars: bool
    websocket: bool
    streaming: bool
    instrument_master: bool
    simulation_only: bool
    research_eligible: bool
    license_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "source_grade": self.source_grade,
            "exchange": self.exchange,
            "timezone": self.timezone,
            "timestamp_semantics": self.timestamp_semantics,
            "realtime_quotes": self.realtime_quotes,
            "historical_bars": self.historical_bars,
            "websocket": self.websocket,
            "streaming": self.streaming,
            "instrument_master": self.instrument_master,
            "simulation_only": self.simulation_only,
            "research_eligible": self.research_eligible,
            "license_status": self.license_status,
        }


@dataclass(frozen=True)
class BrokerCapabilities:
    provider_id: str
    authenticated: bool
    account_read: bool
    positions_read: bool
    orders_read: bool
    trades_read: bool
    place_order: bool = False
    cancel_order: bool = False
    modify_order: bool = False

    def __post_init__(self) -> None:
        if self.place_order or self.cancel_order or self.modify_order:
            raise ValueError("phase15_broker_write_capabilities_forbidden")

    @property
    def can_place_orders(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "authenticated": self.authenticated,
            "account_read": self.account_read,
            "positions_read": self.positions_read,
            "orders_read": self.orders_read,
            "trades_read": self.trades_read,
            "place_order": False,
            "cancel_order": False,
            "modify_order": False,
            "can_place_orders": False,
        }


def assert_no_write_capabilities(caps: BrokerCapabilities) -> None:
    if caps.place_order or caps.cancel_order or caps.modify_order:
        raise ValueError("write_capabilities_not_allowed")
    if caps.can_place_orders:
        raise ValueError("can_place_orders_must_be_false")
