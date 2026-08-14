"""Phase 16A broker capability declarations — write flags fail closed."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from quantfund.phase15.capabilities import BrokerCapabilities, assert_no_write_capabilities


class BrokerCapabilityFlag(str, Enum):
    READ_ACCOUNT = "READ_ACCOUNT"
    READ_POSITIONS = "READ_POSITIONS"
    READ_ORDERS = "READ_ORDERS"
    READ_TRADES = "READ_TRADES"
    READ_MARKET_DATA = "READ_MARKET_DATA"
    READ_HOLDINGS = "READ_HOLDINGS"
    # Future write capabilities — must never be enabled in Phase 16A
    WRITE_PLACE_ORDER = "WRITE_PLACE_ORDER"
    WRITE_CANCEL_ORDER = "WRITE_CANCEL_ORDER"
    WRITE_MODIFY_ORDER = "WRITE_MODIFY_ORDER"


WRITE_FLAGS = frozenset(
    {
        BrokerCapabilityFlag.WRITE_PLACE_ORDER,
        BrokerCapabilityFlag.WRITE_CANCEL_ORDER,
        BrokerCapabilityFlag.WRITE_MODIFY_ORDER,
    }
)

READ_ONLY_DEFAULT = frozenset(
    {
        BrokerCapabilityFlag.READ_ACCOUNT,
        BrokerCapabilityFlag.READ_POSITIONS,
        BrokerCapabilityFlag.READ_ORDERS,
        BrokerCapabilityFlag.READ_TRADES,
        BrokerCapabilityFlag.READ_MARKET_DATA,
        BrokerCapabilityFlag.READ_HOLDINGS,
    }
)


@dataclass(frozen=True)
class DeclaredBrokerCapabilities:
    provider_id: str
    flags: frozenset[BrokerCapabilityFlag]

    def __post_init__(self) -> None:
        bad = self.flags & WRITE_FLAGS
        if bad:
            raise ValueError(
                f"phase16a_write_capabilities_forbidden:{sorted(f.value for f in bad)}"
            )

    @property
    def can_place_orders(self) -> bool:
        return False

    def has(self, flag: BrokerCapabilityFlag) -> bool:
        return flag in self.flags

    def to_phase15(self) -> BrokerCapabilities:
        caps = BrokerCapabilities(
            provider_id=self.provider_id,
            authenticated=True,
            account_read=self.has(BrokerCapabilityFlag.READ_ACCOUNT),
            positions_read=self.has(BrokerCapabilityFlag.READ_POSITIONS),
            orders_read=self.has(BrokerCapabilityFlag.READ_ORDERS),
            trades_read=self.has(BrokerCapabilityFlag.READ_TRADES),
            place_order=False,
            cancel_order=False,
            modify_order=False,
        )
        assert_no_write_capabilities(caps)
        return caps

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "flags": sorted(f.value for f in self.flags),
            "can_place_orders": False,
            "write_capability": "DISABLED",
        }


def declare_readonly_capabilities(
    provider_id: str = "zerodha_kite",
    *,
    flags: Iterable[BrokerCapabilityFlag] | None = None,
) -> DeclaredBrokerCapabilities:
    return DeclaredBrokerCapabilities(
        provider_id=provider_id,
        flags=frozenset(flags) if flags is not None else READ_ONLY_DEFAULT,
    )


def assert_no_write_flags(flags: Iterable[BrokerCapabilityFlag | str]) -> None:
    normalized = {
        f if isinstance(f, BrokerCapabilityFlag) else BrokerCapabilityFlag(str(f))
        for f in flags
    }
    bad = normalized & WRITE_FLAGS
    if bad:
        raise ValueError(
            f"write_capability_detected:{sorted(f.value for f in bad)}"
        )
