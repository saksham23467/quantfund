"""Broker capability declarations — unsupported features fail closed."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CapabilityError(ValueError):
    """Raised when an operation requires an unsupported broker capability."""


class BrokerCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    market_orders: bool = True
    limit_orders: bool = False
    cancel_orders: bool = True
    partial_fills: bool = True
    fractional_quantity: bool = False
    short_selling: bool = False
    order_status_stream: bool = False
    position_query: bool = True
    cash_query: bool = True
    idempotency: bool = True

    def require(self, **flags: bool) -> None:
        for name, needed in flags.items():
            if not needed:
                continue
            if not getattr(self, name, False):
                raise CapabilityError(f"unsupported_capability:{name}")


def phase9_mock_capabilities() -> BrokerCapabilities:
    """Phase 9 v1 Mock: LONG_ONLY + MARKET_ONLY platform contract."""
    return BrokerCapabilities(
        market_orders=True,
        limit_orders=False,
        cancel_orders=True,
        partial_fills=True,
        fractional_quantity=False,
        short_selling=False,
        order_status_stream=False,
        position_query=True,
        cash_query=True,
        idempotency=True,
    )


def validate_order_capabilities(
    caps: BrokerCapabilities,
    *,
    order_type: str,
    side: str,
    quantity: float,
) -> None:
    """Fail closed for LIMIT/SHORT/fractional when unsupported."""
    ot = order_type.upper()
    if ot != "MARKET":
        if ot in {"LIMIT", "STOP", "STOP_LIMIT"} or not caps.limit_orders:
            raise CapabilityError(f"unsupported_order_type:{ot}")
    caps.require(market_orders=True)

    if side.upper() == "SELL" and not caps.short_selling:
        # Sell-to-close is allowed at gateway with position check; naked short blocked there.
        pass

    if not caps.fractional_quantity and abs(quantity - int(quantity)) > 1e-9:
        raise CapabilityError("fractional_quantity_unsupported")

    if caps.short_selling is False and side.upper() not in {"BUY", "SELL"}:
        raise CapabilityError(f"unsupported_side:{side}")
