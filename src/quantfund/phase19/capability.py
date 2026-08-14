"""Runtime capability checks — Phase 19 paper path cannot hold write brokers."""

from __future__ import annotations

from typing import Any

from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.phase19.safety import FORBIDDEN_ADAPTER_TYPES, reject_forbidden_adapter


class CapabilityError(RuntimeError):
    pass


def assert_runtime_paper_capabilities(
    *,
    execution_adapter: Any,
    market_data_provider: Any | None = None,
    readonly_broker: Any | None = None,
) -> dict[str, Any]:
    """Fail closed if any write-capable component is attached."""
    reject_forbidden_adapter(execution_adapter)
    if not isinstance(execution_adapter, PaperExecutionAdapter):
        raise CapabilityError(
            f"execution_adapter_must_be_PaperExecutionAdapter_got_{type(execution_adapter).__name__}"
        )

    if market_data_provider is not None:
        reject_forbidden_adapter(market_data_provider)
        if getattr(market_data_provider, "can_place_orders", False) is True:
            raise CapabilityError("market_data_provider_can_place_orders")

    if readonly_broker is not None:
        reject_forbidden_adapter(readonly_broker)
        if getattr(readonly_broker, "can_place_orders", None) is True:
            raise CapabilityError("readonly_broker_can_place_orders")
        name = type(readonly_broker).__name__
        if name in FORBIDDEN_ADAPTER_TYPES:
            raise CapabilityError(f"forbidden_broker:{name}")
        # Read-only stubs may define place_order that raises — must never succeed
        if hasattr(readonly_broker, "place_order"):
            try:
                readonly_broker.place_order()  # type: ignore[misc]
            except Exception:  # noqa: BLE001 — any raise is required
                pass
            else:
                raise CapabilityError("readonly_broker_place_order_succeeded")

    return {
        "execution_adapter": type(execution_adapter).__name__,
        "can_place_orders": False,
        "live_trading": False,
        "ok": True,
    }
