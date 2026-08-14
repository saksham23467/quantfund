"""Map QuantFund internal orders ↔ Kite params; map Kite statuses → BrokerOrderState."""

from __future__ import annotations

from quantfund.brokers.base import BrokerOrderRequest, UnsupportedBrokerOrderError, assert_supported_nse_equity_cnc
from quantfund.execution.live_orders import BrokerOrderState
from quantfund.trading.models import OrderSide, OrderType

# Kite status → internal (unknown → UNKNOWN, never silent FILLED)
_KITE_STATUS_MAP: dict[str, BrokerOrderState] = {
    "PUT ORDER REQ RECEIVED": BrokerOrderState.SUBMITTED,
    "VALIDATION PENDING": BrokerOrderState.SUBMITTED,
    "OPEN PENDING": BrokerOrderState.SUBMITTED,
    "MODIFY VALIDATION PENDING": BrokerOrderState.OPEN,
    "MODIFY PENDING": BrokerOrderState.OPEN,
    "TRIGGER PENDING": BrokerOrderState.OPEN,
    "CANCEL PENDING": BrokerOrderState.CANCEL_PENDING,
    "AMO REQ RECEIVED": BrokerOrderState.SUBMITTED,
    "OPEN": BrokerOrderState.OPEN,
    "COMPLETE": BrokerOrderState.FILLED,
    "CANCELLED": BrokerOrderState.CANCELLED,
    "REJECTED": BrokerOrderState.REJECTED,
    "EXPIRED": BrokerOrderState.EXPIRED,
    # common lowercase aliases
    "open": BrokerOrderState.OPEN,
    "complete": BrokerOrderState.FILLED,
    "cancelled": BrokerOrderState.CANCELLED,
    "canceled": BrokerOrderState.CANCELLED,
    "rejected": BrokerOrderState.REJECTED,
    "expired": BrokerOrderState.EXPIRED,
}


def map_kite_status(status: str | None) -> BrokerOrderState:
    if status is None or str(status).strip() == "":
        return BrokerOrderState.UNKNOWN
    raw = str(status).strip()
    if raw in _KITE_STATUS_MAP:
        return _KITE_STATUS_MAP[raw]
    upper = raw.upper()
    if upper in _KITE_STATUS_MAP:
        return _KITE_STATUS_MAP[upper]
    # Partial fill is conveyed via filled_quantity vs quantity, not always status
    if "PARTIAL" in upper:
        return BrokerOrderState.PARTIALLY_FILLED
    return BrokerOrderState.UNKNOWN


def refine_state_with_fills(
    state: BrokerOrderState,
    *,
    quantity: float,
    filled_quantity: float,
) -> BrokerOrderState:
    if state in {
        BrokerOrderState.CANCELLED,
        BrokerOrderState.REJECTED,
        BrokerOrderState.EXPIRED,
        BrokerOrderState.UNKNOWN,
    }:
        return state
    if filled_quantity <= 0:
        return state
    if filled_quantity + 1e-9 >= quantity:
        return BrokerOrderState.FILLED
    return BrokerOrderState.PARTIALLY_FILLED


def to_kite_order_params(request: BrokerOrderRequest) -> dict:
    """Translate internal request to Kite place_order kwargs. Fail closed."""
    assert_supported_nse_equity_cnc(request)
    if request.product.upper() != "CNC":
        raise UnsupportedBrokerOrderError("derivatives_not_supported")

    txn = "BUY" if request.side == OrderSide.BUY else "SELL"
    otype = "MARKET" if request.order_type == OrderType.MARKET else "LIMIT"
    params = {
        "variety": "regular",
        "exchange": "NSE",
        "tradingsymbol": request.symbol.upper(),
        "transaction_type": txn,
        "quantity": int(request.quantity),
        "order_type": otype,
        "product": "CNC",
        "validity": "DAY",
        "price": 0.0 if otype == "MARKET" else float(request.price or 0.0),
        "trigger_price": float(request.trigger_price or 0.0),
        "tag": (request.tag or request.execution_intent_id)[:20],
    }
    return params


def side_from_kite(txn: str) -> OrderSide:
    t = (txn or "").upper()
    if t == "BUY":
        return OrderSide.BUY
    if t == "SELL":
        return OrderSide.SELL
    raise UnsupportedBrokerOrderError(f"unsupported_transaction_type:{txn}")
