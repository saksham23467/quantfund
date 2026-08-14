"""DRY_RUN transport — validate and record, never send to an exchange.

Distinct from Phase 8 PaperExecutionAdapter (simulated fills without broker protocol).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.execution.broker_adapter import (
    BrokerAdapter,
    CancelOrderRequest,
    CancelOrderResponse,
    GetOpenOrdersRequest,
    GetOrderRequest,
    ReconcileRequest,
    SubmitOrderRequest,
    SubmitOrderResponse,
    assert_mock_only,
)
from quantfund.execution.live_orders import BrokerOrderState


@dataclass
class DryRunTransport:
    """Wraps MockBroker: submissions are protocol-valid but counted as dry_run.

    ``real_orders_sent`` is always 0. Selecting a non-mock adapter fails closed.
    """

    broker: BrokerAdapter
    requests: list[SubmitOrderRequest] = field(default_factory=list)
    responses: list[SubmitOrderResponse] = field(default_factory=list)
    real_orders_sent: int = 0

    def __post_init__(self) -> None:
        assert_mock_only(self.broker.adapter_id)
        if getattr(self.broker, "real_orders_sent", 0) != 0:
            raise ValueError("broker_already_sent_real_orders")

    def submit(self, request: SubmitOrderRequest) -> SubmitOrderResponse:
        assert_mock_only(self.broker.adapter_id)
        self.requests.append(request)
        # Call mock for state machine exercise, but mark dry_run and never increment real sends
        raw = self.broker.submit_order(request)
        resp = SubmitOrderResponse(
            client_order_id=raw.client_order_id,
            broker_order_id=raw.broker_order_id,
            state=raw.state,
            reject_reason=raw.reject_reason,
            filled_quantity=raw.filled_quantity,
            avg_price=raw.avg_price,
            dry_run=True,
        )
        self.responses.append(resp)
        self.real_orders_sent = 0
        return resp

    def cancel(self, request: CancelOrderRequest) -> CancelOrderResponse:
        assert_mock_only(self.broker.adapter_id)
        return self.broker.cancel_order(request)

    def get_order(self, request: GetOrderRequest):
        return self.broker.get_order(request)

    def get_open_orders(self, request: GetOpenOrdersRequest):
        return self.broker.get_open_orders(request)

    def reconcile(self, request: ReconcileRequest):
        return self.broker.reconcile(request)

    def stats(self) -> dict[str, Any]:
        return {
            "dry_run_submits": len(self.requests),
            "real_orders_sent": self.real_orders_sent,
            "unknown_count": sum(
                1 for r in self.responses if r.state == BrokerOrderState.UNKNOWN
            ),
        }
