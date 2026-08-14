"""Read-only broker adapter — write methods do not exist / cannot succeed."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quantfund.phase15.capabilities import BrokerCapabilities, assert_no_write_capabilities


class BrokerWriteForbidden(RuntimeError):
    """Raised if any write path is attempted in Phase 15."""


@dataclass
class BrokerAccountSnapshot:
    cash: float | None = None
    positions: dict[str, float] = field(default_factory=dict)
    orders: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    connected: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash": self.cash,
            "positions": dict(self.positions),
            "orders": list(self.orders),
            "trades": list(self.trades),
            "connected": self.connected,
            "detail": self.detail,
        }


class ReadOnlyBrokerAdapter(ABC):
    """Narrow read-only broker surface. No place/cancel/modify methods."""

    @abstractmethod
    def capabilities(self) -> BrokerCapabilities: ...

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def health(self) -> dict[str, Any]: ...

    @abstractmethod
    def get_account(self) -> BrokerAccountSnapshot: ...

    @abstractmethod
    def get_positions(self) -> dict[str, float]: ...

    @abstractmethod
    def get_orders(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_trades(self) -> list[dict[str, Any]]: ...

    # Explicitly absent write API — methods that raise if called via getattr misuse
    def place_order(self, *args: Any, **kwargs: Any) -> None:
        raise BrokerWriteForbidden("phase15_place_order_forbidden")

    def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        raise BrokerWriteForbidden("phase15_cancel_order_forbidden")

    def modify_order(self, *args: Any, **kwargs: Any) -> None:
        raise BrokerWriteForbidden("phase15_modify_order_forbidden")

    @property
    def can_place_orders(self) -> bool:
        return False


class SimulatedReadOnlyBroker(ReadOnlyBrokerAdapter):
    """CI / demo broker — always read-only, no network."""

    def __init__(
        self,
        *,
        cash: float = 100_000.0,
        positions: dict[str, float] | None = None,
    ) -> None:
        self._cash = cash
        self._positions = dict(positions or {})
        self._connected = False
        self._orders: list[dict[str, Any]] = []
        self._trades: list[dict[str, Any]] = []

    def capabilities(self) -> BrokerCapabilities:
        caps = BrokerCapabilities(
            provider_id="simulated_readonly",
            authenticated=True,
            account_read=True,
            positions_read=True,
            orders_read=True,
            trades_read=True,
            place_order=False,
            cancel_order=False,
            modify_order=False,
        )
        assert_no_write_capabilities(caps)
        return caps

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def health(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "provider": "simulated_readonly",
            "can_place_orders": False,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def get_account(self) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(
            cash=self._cash,
            positions=dict(self._positions),
            orders=list(self._orders),
            trades=list(self._trades),
            connected=self._connected,
            detail="simulated",
        )

    def get_positions(self) -> dict[str, float]:
        return dict(self._positions)

    def get_orders(self) -> list[dict[str, Any]]:
        return list(self._orders)

    def get_trades(self) -> list[dict[str, Any]]:
        return list(self._trades)

    def set_positions_for_tests(self, positions: dict[str, float]) -> None:
        """Test/demo helper — does not submit orders."""
        self._positions = dict(positions)


def construct_readonly_broker(
    *,
    mode: str = "simulated",
    env: dict[str, str] | None = None,
) -> ReadOnlyBrokerAdapter:
    """Factory — never returns a write-capable broker in Phase 15."""
    if mode in {"simulated", "sim", "fallback"}:
        return SimulatedReadOnlyBroker()
    # Real credentials path: still wrap as read-only fail-closed stub for Phase 15
    # without calling place_order. Full Zerodha read wiring stays optional.
    env = env or {}
    # Credentials may exist for future read-only connectivity checks, but Phase 15
    # demo/CI always uses SimulatedReadOnlyBroker (no write SDK path).
    _ = env
    return SimulatedReadOnlyBroker()
