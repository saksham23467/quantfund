"""ExecutionRouter — Strategy-facing intent routing to paper or Zerodha.

Strategy never knows which path executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quantfund.brokers.base import BrokerExecutionAdapter, BrokerOrderRequest
from quantfund.brokers.intent_store import ExecutionIntentStore
from quantfund.execution.broker_adapter import BrokerHealth, BrokerOrderView
from quantfund.execution.live_guard import LiveExecutionGuard, LiveGuardDecision
from quantfund.execution.modes import QuantFundExecutionMode
from quantfund.paper.execution import ExecutionResult, PaperExecutionAdapter
from quantfund.paper.orders import OrderIntent
from quantfund.trading.models import OrderSide, OrderType


@dataclass
class RouterSubmitResult:
    path: str  # paper | zerodha | blocked
    accepted: bool
    reason: str | None = None
    broker_order: BrokerOrderView | None = None
    paper_result: ExecutionResult | None = None
    guard: LiveGuardDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "accepted": self.accepted,
            "reason": self.reason,
            "broker_order_id": (
                self.broker_order.broker_order_id if self.broker_order else None
            ),
            "guard": self.guard.to_dict() if self.guard else None,
        }


class ExecutionRouter:
    """Routes ExecutionIntent to PaperExecutionAdapter or ZerodhaExecutionAdapter."""

    def __init__(
        self,
        *,
        mode: QuantFundExecutionMode,
        paper: PaperExecutionAdapter | None = None,
        broker: BrokerExecutionAdapter | None = None,
        guard: LiveExecutionGuard | None = None,
        intent_store: ExecutionIntentStore | None = None,
    ) -> None:
        self.mode = mode
        self.paper = paper
        self.broker = broker
        self.guard = guard
        self.intent_store = intent_store or ExecutionIntentStore()

    def route_broker_request(
        self,
        request: BrokerOrderRequest,
        *,
        ref_price: float,
    ) -> RouterSubmitResult:
        if self.mode in {QuantFundExecutionMode.OFF}:
            return RouterSubmitResult(
                path="blocked", accepted=False, reason="execution_mode_off"
            )
        if self.mode == QuantFundExecutionMode.SIMULATION:
            return RouterSubmitResult(
                path="paper",
                accepted=False,
                reason="use_paper_execute_at_open_for_simulation",
            )

        if self.broker is None or self.guard is None:
            return RouterSubmitResult(
                path="blocked", accepted=False, reason="broker_or_guard_missing"
            )

        # Idempotent short-circuit: return existing broker order, never re-submit
        existing = self.intent_store.get(request.execution_intent_id)
        if existing and existing.broker_order_id:
            view = self.broker.get_order(broker_order_id=existing.broker_order_id)
            return RouterSubmitResult(
                path="zerodha",
                accepted=True,
                reason="idempotent_existing_order",
                broker_order=view,
            )

        health: BrokerHealth = self.broker.health()
        decision = self.guard.check(request, health=health, ref_price=ref_price)
        if not decision.allowed:
            return RouterSubmitResult(
                path="blocked",
                accepted=False,
                reason=decision.reason,
                guard=decision,
            )

        view = self.broker.place_order(request)
        self.guard.record_accepted(request, ref_price=ref_price)
        return RouterSubmitResult(
            path="zerodha",
            accepted=True,
            reason=None,
            broker_order=view,
            guard=decision,
        )

    def intent_to_broker_request(
        self,
        intent: OrderIntent,
        *,
        exchange: str = "NSE",
        product: str = "CNC",
        price: float | None = None,
    ) -> BrokerOrderRequest:
        order = intent.order
        otype = order.order_type
        if otype not in {OrderType.MARKET, OrderType.LIMIT}:
            otype = OrderType.MARKET
        return BrokerOrderRequest(
            execution_intent_id=intent.intent_id,
            instrument_id=order.metadata.get("instrument_id")
            or f"{exchange}:{order.symbol}",
            exchange=exchange,
            symbol=order.symbol,
            side=order.side if isinstance(order.side, OrderSide) else OrderSide.BUY,
            quantity=int(order.quantity),
            order_type=otype,
            price=price,
            product=product,
            validity="DAY",
            metadata={"session_id": intent.session_id},
        )
