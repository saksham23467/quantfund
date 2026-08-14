"""Order intent dry-run — shows what WOULD be sent; never submits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.brokers.base import BrokerOrderRequest, assert_supported_nse_equity_cnc
from quantfund.brokers.zerodha.mapper import to_kite_order_params
from quantfund.execution.live_guard import LiveExecutionGuard, LiveGuardDecision
from quantfund.production.controls import ControlDecision, ProductionTradingControls
from quantfund.trading.models import OrderType


DRY_RUN_BANNER = """
╔══════════════════════════════════════════════════════════════╗
║  ZERODHA ORDER DRY-RUN — NOT A REAL ORDER                    ║
║  NO BROKER SUBMISSION OCCURRED                               ║
╚══════════════════════════════════════════════════════════════╝
""".strip()


@dataclass
class OrderDryRunResult:
    would_send: dict[str, Any]
    execution_intent_id: str
    risk_checks: dict[str, Any]
    estimated_costs: dict[str, float]
    submitted: bool = False
    banner: str = DRY_RUN_BANNER

    def to_dict(self) -> dict[str, Any]:
        return {
            "banner": self.banner,
            "submitted": self.submitted,
            "execution_intent_id": self.execution_intent_id,
            "would_send": dict(self.would_send),
            "risk_checks": dict(self.risk_checks),
            "estimated_costs": dict(self.estimated_costs),
            "WARNING": "DRY-RUN ONLY — NOT SUBMITTED TO ZERODHA",
        }


def estimate_costs(
    *,
    quantity: float,
    price: float,
    side: str,
    brokerage_bps: float = 3.0,
) -> dict[str, float]:
    notional = abs(quantity * price)
    brokerage = notional * brokerage_bps / 10_000.0
    # Simplified illustrative India equity delivery estimate (not a quote)
    stt = notional * 0.001 if side.upper() == "SELL" else 0.0
    return {
        "notional": notional,
        "brokerage_est": brokerage,
        "stt_est": stt,
        "total_est": brokerage + stt,
    }


def dry_run_order(
    request: BrokerOrderRequest,
    *,
    ref_price: float,
    controls: ProductionTradingControls | None = None,
    guard: LiveExecutionGuard | None = None,
    guard_decision: LiveGuardDecision | None = None,
    control_decision: ControlDecision | None = None,
) -> OrderDryRunResult:
    assert_supported_nse_equity_cnc(request)
    kite = to_kite_order_params(request)
    price = float(request.price or ref_price)
    if request.order_type == OrderType.MARKET:
        price = float(ref_price)

    risk: dict[str, Any] = {}
    if controls is not None:
        cd = control_decision or controls.check_new_order(request, ref_price=ref_price)
        risk["production_controls"] = cd.to_dict()
    if guard is not None and guard_decision is not None:
        risk["live_guard"] = guard_decision.to_dict()

    return OrderDryRunResult(
        would_send={
            "symbol": request.symbol,
            "exchange": request.exchange,
            "side": request.side.value,
            "quantity": request.quantity,
            "order_type": request.order_type.value,
            "price": request.price,
            "product": request.product,
            "validity": request.validity,
            "execution_intent_id": request.execution_intent_id,
            "kite_params": kite,
        },
        execution_intent_id=request.execution_intent_id,
        risk_checks=risk,
        estimated_costs=estimate_costs(
            quantity=float(request.quantity),
            price=price,
            side=request.side.value,
        ),
        submitted=False,
    )


def format_dry_run(result: OrderDryRunResult) -> str:
    lines = [
        result.banner,
        "",
        f"execution_intent_id: {result.execution_intent_id}",
        f"submitted: {result.submitted}",
        "",
        "WOULD SEND (Kite params):",
    ]
    for k, v in result.would_send.get("kite_params", {}).items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("Risk checks:")
    for k, v in result.risk_checks.items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("Estimated costs:")
    for k, v in result.estimated_costs.items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("*** DRY-RUN COMPLETE — ORDER SUBMISSION: NOT EXECUTED ***")
    return "\n".join(lines)
