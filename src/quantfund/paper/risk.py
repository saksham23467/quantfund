"""Paper risk layer — wraps existing RiskEngine; never raises platform ceilings."""

from __future__ import annotations

from dataclasses import dataclass

from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.orders import OrderIntent, PaperOrderStatus
from quantfund.risk.limits import RiskConfig, RiskDecision, RiskEngine
from quantfund.trading.models import OrderSide, OrderStatus


@dataclass(frozen=True)
class PaperRiskConfig:
    """Session-scoped paper ceilings (may only reduce relative to strategy asks)."""

    max_position_quantity: float = 1_000_000.0
    max_position_notional: float = 100_000.0
    max_order_notional: float = 100_000.0
    max_gross_exposure: float = 100_000.0
    max_daily_loss: float | None = None  # absolute equity drawdown from day start
    max_turnover: float | None = None  # cumulative |notional| traded in session
    max_order_count: int | None = None

    def to_core_risk_config(self) -> RiskConfig:
        return RiskConfig(
            max_order_value=self.max_order_notional,
            max_position_value=self.max_position_notional,
            max_total_exposure=self.max_gross_exposure,
            max_daily_loss=self.max_daily_loss,
            kill_switch=False,  # owned by paper KillSwitch
        )


@dataclass
class PaperRiskDecision:
    accepted: bool
    intent: OrderIntent
    reason: str | None = None
    clipped_quantity: float | None = None


class PaperRiskEngine:
    """Compose KillSwitch + existing RiskEngine + paper-specific ceilings."""

    def __init__(
        self,
        config: PaperRiskConfig | None = None,
        *,
        kill_switch: KillSwitch | None = None,
        core: RiskEngine | None = None,
    ) -> None:
        self.config = config or PaperRiskConfig()
        self.kill_switch = kill_switch or KillSwitch()
        self.core = core or RiskEngine(self.config.to_core_risk_config())
        self.order_count = 0
        self.turnover = 0.0
        self.day_start_equity: float | None = None

    def set_day_start_equity(self, equity: float) -> None:
        self.day_start_equity = equity

    def check_intent(
        self,
        intent: OrderIntent,
        *,
        ref_price: float,
        current_position_qty: float,
        current_exposure: float,
        current_equity: float,
    ) -> PaperRiskDecision:
        if intent.status not in {PaperOrderStatus.CREATED, PaperOrderStatus.VALIDATED}:
            return PaperRiskDecision(
                False, intent, reason="invalid_intent_status_for_risk"
            )

        if self.kill_switch.is_triggered:
            intent.transition(PaperOrderStatus.REJECTED, reason="kill_switch")
            return PaperRiskDecision(False, intent, reason="kill_switch")

        if self.config.max_order_count is not None and (
            self.order_count >= self.config.max_order_count
        ):
            intent.transition(PaperOrderStatus.REJECTED, reason="max_order_count")
            return PaperRiskDecision(False, intent, reason="max_order_count")

        if ref_price <= 0:
            intent.transition(PaperOrderStatus.REJECTED, reason="invalid_ref_price")
            return PaperRiskDecision(False, intent, reason="invalid_ref_price")

        order_notional = intent.order.quantity * ref_price
        if order_notional > self.config.max_order_notional + 1e-9:
            intent.transition(PaperOrderStatus.REJECTED, reason="max_order_notional")
            return PaperRiskDecision(False, intent, reason="max_order_notional")

        if intent.order.side == OrderSide.BUY:
            new_qty = current_position_qty + intent.order.quantity
        else:
            new_qty = current_position_qty - intent.order.quantity
        if new_qty > self.config.max_position_quantity + 1e-9:
            intent.transition(PaperOrderStatus.REJECTED, reason="max_position_quantity")
            return PaperRiskDecision(False, intent, reason="max_position_quantity")

        if self.config.max_turnover is not None:
            projected = self.turnover + order_notional
            if projected > self.config.max_turnover + 1e-9:
                intent.transition(PaperOrderStatus.REJECTED, reason="max_turnover")
                return PaperRiskDecision(False, intent, reason="max_turnover")

        if (
            self.config.max_daily_loss is not None
            and self.day_start_equity is not None
        ):
            loss = self.day_start_equity - current_equity
            if loss > self.config.max_daily_loss + 1e-9:
                intent.transition(PaperOrderStatus.REJECTED, reason="max_daily_loss")
                return PaperRiskDecision(False, intent, reason="max_daily_loss")

        # Delegate overlapping notional checks to existing RiskEngine (never bypass)
        core_decision: RiskDecision = self.core.check_order(
            intent.order,
            ref_price=ref_price,
            current_position_qty=current_position_qty,
            current_exposure=current_exposure,
        )
        if not core_decision.accepted:
            reason = core_decision.reason or "risk_rejected"
            # Map core reason names to paper vocabulary where useful
            mapped = {
                "max_order_value": "max_order_notional",
                "max_position_value": "max_position_notional",
                "max_total_exposure": "max_gross_exposure",
            }.get(reason, reason)
            intent.order = core_decision.order
            if intent.status != PaperOrderStatus.REJECTED:
                intent.transition(PaperOrderStatus.REJECTED, reason=mapped)
            return PaperRiskDecision(False, intent, reason=mapped)

        intent.order = core_decision.order
        # Core sets ACCEPTED on trading.Order; paper stays VALIDATED until session accepts
        if intent.order.status == OrderStatus.ACCEPTED:
            intent.order.status = OrderStatus.PENDING
        return PaperRiskDecision(True, intent, reason=None)

    def record_accepted(self, intent: OrderIntent, *, ref_price: float) -> None:
        self.order_count += 1
        self.turnover += intent.order.quantity * ref_price
