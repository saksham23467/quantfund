"""MockBrokerAdapter — sole broker implementation in Phase 9 v1.

Supports scripted fills, rejects, timeouts (UNKNOWN), partials, disconnects.
No network. No real credentials. No exchange connectivity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from quantfund.execution.broker_adapter import (
    BrokerCashView,
    BrokerHealth,
    BrokerOrderView,
    BrokerPositionView,
    BrokerReconcileSnapshot,
    CancelOrderRequest,
    CancelOrderResponse,
    GetOpenOrdersRequest,
    GetOrderRequest,
    ReconcileRequest,
    SubmitOrderRequest,
    SubmitOrderResponse,
)
from quantfund.execution.capabilities import (
    BrokerCapabilities,
    phase9_mock_capabilities,
    validate_order_capabilities,
)
from quantfund.execution.live_orders import BrokerOrderState, make_client_order_id
from quantfund.trading.models import OrderSide


class MockBehavior(str, Enum):
    FILL = "fill"
    PARTIAL = "partial"
    REJECT = "reject"
    TIMEOUT_UNKNOWN = "timeout_unknown"
    DISCONNECT = "disconnect"


@dataclass
class MockBrokerAdapter:
    """In-process deterministic mock venue."""

    initial_cash: float = 100_000.0
    behavior: MockBehavior = MockBehavior.FILL
    partial_ratio: float = 0.5
    reject_reason: str = "mock_reject"
    _connected: bool = False
    _orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    _positions: dict[str, float] = field(default_factory=dict)
    _avg: dict[str, float] = field(default_factory=dict)
    _cash: float = 100_000.0
    _submit_count: int = 0
    real_orders_sent: int = 0  # always 0 for mock
    _seq: int = 0

    def __post_init__(self) -> None:
        self._cash = self.initial_cash

    @property
    def adapter_id(self) -> str:
        return "mock"

    def capabilities(self) -> BrokerCapabilities:
        return phase9_mock_capabilities()

    def connect(self) -> BrokerHealth:
        if self.behavior == MockBehavior.DISCONNECT:
            self._connected = False
            return BrokerHealth(
                connected=False,
                degraded=True,
                reason="mock_disconnect",
                adapter_id=self.adapter_id,
            )
        self._connected = True
        return BrokerHealth(
            connected=True,
            adapter_id=self.adapter_id,
            server_time=datetime.now(timezone.utc),
        )

    def disconnect(self) -> None:
        self._connected = False

    def health(self) -> BrokerHealth:
        return BrokerHealth(
            connected=self._connected,
            degraded=self.behavior == MockBehavior.DISCONNECT,
            reason=None if self._connected else "disconnected",
            adapter_id=self.adapter_id,
        )

    def submit_order(self, request: SubmitOrderRequest) -> SubmitOrderResponse:
        self._submit_count += 1
        # Never a real network order
        assert self.real_orders_sent == 0

        if not self._connected or self.behavior == MockBehavior.DISCONNECT:
            return SubmitOrderResponse(
                client_order_id=request.client_order_id,
                state=BrokerOrderState.UNKNOWN,
                reject_reason="broker_disconnected",
                dry_run=False,
            )

        validate_order_capabilities(
            self.capabilities(),
            order_type=request.order_type.value,
            side=request.side.value,
            quantity=request.quantity,
        )

        if self.behavior == MockBehavior.TIMEOUT_UNKNOWN:
            self._orders[request.client_order_id] = {
                "request": request,
                "state": BrokerOrderState.UNKNOWN,
                "filled": 0.0,
                "broker_order_id": None,
            }
            return SubmitOrderResponse(
                client_order_id=request.client_order_id,
                state=BrokerOrderState.UNKNOWN,
                reject_reason="timeout_unknown",
            )

        if self.behavior == MockBehavior.REJECT:
            self._orders[request.client_order_id] = {
                "request": request,
                "state": BrokerOrderState.REJECTED,
                "filled": 0.0,
                "broker_order_id": None,
            }
            return SubmitOrderResponse(
                client_order_id=request.client_order_id,
                state=BrokerOrderState.REJECTED,
                reject_reason=self.reject_reason,
            )

        self._seq += 1
        broker_order_id = make_client_order_id(
            session_id=request.session_id,
            intent_id=f"broker|{request.intent_id}",
            submit_epoch=self._seq,
        )
        price = request.ref_price if request.ref_price and request.ref_price > 0 else 100.0

        if self.behavior == MockBehavior.PARTIAL:
            filled = request.quantity * self.partial_ratio
            state = BrokerOrderState.PARTIALLY_FILLED
        else:
            filled = request.quantity
            state = BrokerOrderState.FILLED

        # Update mock portfolio (long-only)
        if request.side == OrderSide.BUY:
            cost = filled * price
            if cost > self._cash + 1e-9:
                self._orders[request.client_order_id] = {
                    "request": request,
                    "state": BrokerOrderState.REJECTED,
                    "filled": 0.0,
                    "broker_order_id": None,
                }
                return SubmitOrderResponse(
                    client_order_id=request.client_order_id,
                    state=BrokerOrderState.REJECTED,
                    reject_reason="insufficient_cash",
                )
            prev = self._positions.get(request.symbol, 0.0)
            new_qty = prev + filled
            if prev == 0:
                self._avg[request.symbol] = price
            else:
                self._avg[request.symbol] = (
                    self._avg.get(request.symbol, price) * prev + price * filled
                ) / new_qty
            self._positions[request.symbol] = new_qty
            self._cash -= cost
        else:
            pos = self._positions.get(request.symbol, 0.0)
            if filled > pos + 1e-9:
                self._orders[request.client_order_id] = {
                    "request": request,
                    "state": BrokerOrderState.REJECTED,
                    "filled": 0.0,
                    "broker_order_id": None,
                }
                return SubmitOrderResponse(
                    client_order_id=request.client_order_id,
                    state=BrokerOrderState.REJECTED,
                    reject_reason="insufficient_position",
                )
            self._positions[request.symbol] = pos - filled
            self._cash += filled * price

        self._orders[request.client_order_id] = {
            "request": request,
            "state": state,
            "filled": filled,
            "broker_order_id": broker_order_id,
            "avg_price": price,
        }
        return SubmitOrderResponse(
            client_order_id=request.client_order_id,
            broker_order_id=broker_order_id,
            state=state,
            filled_quantity=filled,
            avg_price=price,
        )

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResponse:
        rec = self._orders.get(request.client_order_id)
        if rec is None:
            return CancelOrderResponse(
                client_order_id=request.client_order_id,
                state=BrokerOrderState.UNKNOWN,
                reject_reason="order_not_found",
            )
        if rec["state"] in {
            BrokerOrderState.FILLED,
            BrokerOrderState.REJECTED,
            BrokerOrderState.CANCELLED,
        }:
            return CancelOrderResponse(
                client_order_id=request.client_order_id,
                state=rec["state"],
                reject_reason="already_terminal",
            )
        rec["state"] = BrokerOrderState.CANCELLED
        return CancelOrderResponse(
            client_order_id=request.client_order_id,
            state=BrokerOrderState.CANCELLED,
        )

    def get_order(self, request: GetOrderRequest) -> BrokerOrderView:
        rec = self._orders.get(request.client_order_id)
        if rec is None:
            return BrokerOrderView(
                client_order_id=request.client_order_id,
                symbol="",
                side=OrderSide.BUY,
                quantity=0,
                state=BrokerOrderState.UNKNOWN,
            )
        req: SubmitOrderRequest = rec["request"]
        return BrokerOrderView(
            client_order_id=request.client_order_id,
            broker_order_id=rec.get("broker_order_id"),
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
            filled_quantity=float(rec.get("filled", 0.0)),
            state=rec["state"],
            avg_price=rec.get("avg_price"),
            updated_at=datetime.now(timezone.utc),
        )

    def get_open_orders(self, request: GetOpenOrdersRequest) -> list[BrokerOrderView]:
        out: list[BrokerOrderView] = []
        for cid, rec in self._orders.items():
            if rec["state"] in {
                BrokerOrderState.ACKNOWLEDGED,
                BrokerOrderState.PARTIALLY_FILLED,
                BrokerOrderState.SUBMITTED,
                BrokerOrderState.CANCEL_PENDING,
            }:
                out.append(self.get_order(GetOrderRequest(client_order_id=cid)))
        return out

    def get_positions(self) -> list[BrokerPositionView]:
        return [
            BrokerPositionView(
                symbol=sym,
                quantity=qty,
                average_entry_price=self._avg.get(sym, 0.0),
            )
            for sym, qty in sorted(self._positions.items())
            if abs(qty) > 1e-12
        ]

    def get_cash(self) -> BrokerCashView:
        return BrokerCashView(
            cash=self._cash,
            as_of=datetime.now(timezone.utc),
        )

    def reconcile(self, request: ReconcileRequest) -> BrokerReconcileSnapshot:
        return BrokerReconcileSnapshot(
            positions=self.get_positions(),
            cash=self.get_cash(),
            open_orders=self.get_open_orders(
                GetOpenOrdersRequest(session_id=request.session_id)
            ),
        )
