"""PaperExecutionAdapter — sole paper fill factory. No brokers / no live transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from quantfund.backtest.broker_sim import SlippageModel
from quantfund.backtest.costs import CostModel, EquityDeliveryCostModel, MarketSegment
from quantfund.paper.fills import (
    PaperFillConfig,
    build_fill,
    compute_fill_quantity,
    make_fill_id,
)
from quantfund.paper.models import PartialFillPolicy
from quantfund.paper.orders import OrderIntent, PaperOrderStatus
from quantfund.research.execution_models import resolve_execution_models
from quantfund.trading.models import Fill, OrderSide


@dataclass
class ExecutionResult:
    intent: OrderIntent
    fill: Fill | None
    rejected: bool
    reason: str | None = None


class PaperExecutionAdapter:
    """Simulated venue for paper sessions.

    Only this class may create Fill objects in paper mode.
    Strategies must never import or call this adapter.
    """

    def __init__(
        self,
        *,
        session_id: str,
        cost_model: CostModel | None = None,
        slippage_model: SlippageModel | None = None,
        fill_config: PaperFillConfig | None = None,
        cost_model_id: str = "equity_delivery_v1",
        slippage_model_id: str = "fixed_bps_5",
    ) -> None:
        if cost_model is None or slippage_model is None:
            cost_model, slippage_model = resolve_execution_models(
                cost_model=cost_model_id,
                slippage_model=slippage_model_id,
            )
        self.session_id = session_id
        self.cost_model = cost_model or EquityDeliveryCostModel()
        self.slippage_model = slippage_model or SlippageModel()
        self.fill_config = fill_config or PaperFillConfig()
        self._fill_seq = 0
        self._applied_fill_ids: set[str] = set()

    @property
    def applied_fill_ids(self) -> set[str]:
        return set(self._applied_fill_ids)

    def execute_at_open(
        self,
        intent: OrderIntent,
        *,
        execution_time: datetime,
        open_price: float,
        cash: float,
        position_qty: float,
        market_closed: bool = False,
        stale: bool = False,
    ) -> ExecutionResult:
        if intent.status not in {
            PaperOrderStatus.ACCEPTED,
            PaperOrderStatus.PARTIALLY_FILLED,
        }:
            return ExecutionResult(
                intent, None, True, reason=f"invalid_status_{intent.status.value}"
            )

        if market_closed and self.fill_config.reject_on_market_closed:
            intent.transition(PaperOrderStatus.REJECTED, reason="market_closed")
            return ExecutionResult(intent, None, True, reason="market_closed")

        if stale and self.fill_config.reject_on_stale_data:
            intent.transition(PaperOrderStatus.REJECTED, reason="stale_data")
            return ExecutionResult(intent, None, True, reason="stale_data")

        if open_price <= 0:
            intent.transition(PaperOrderStatus.REJECTED, reason="invalid_open_price")
            return ExecutionResult(intent, None, True, reason="invalid_open_price")

        qty = compute_fill_quantity(
            remaining_quantity=intent.remaining_quantity,
            policy=self.fill_config.partial_fill_policy,
            ratio=self.fill_config.partial_fill_ratio,
        )
        if qty <= 0:
            intent.transition(PaperOrderStatus.REJECTED, reason="zero_fill_quantity")
            return ExecutionResult(intent, None, True, reason="zero_fill_quantity")

        fill_price, slip = self.slippage_model.apply(
            side=intent.order.side, price=open_price
        )
        costs = self.cost_model.compute(
            side=intent.order.side,
            quantity=qty,
            price=fill_price,
            segment=MarketSegment.EQUITY_DELIVERY,
        )

        if intent.order.side == OrderSide.BUY:
            needed = qty * fill_price + costs.total
            if self.fill_config.reject_on_insufficient_cash and needed > cash + 1e-9:
                intent.transition(PaperOrderStatus.REJECTED, reason="insufficient_cash")
                return ExecutionResult(intent, None, True, reason="insufficient_cash")
        else:
            if (
                self.fill_config.reject_on_insufficient_position
                and qty > position_qty + 1e-9
            ):
                intent.transition(
                    PaperOrderStatus.REJECTED, reason="insufficient_position"
                )
                return ExecutionResult(
                    intent, None, True, reason="insufficient_position"
                )

        self._fill_seq += 1
        fill_id = make_fill_id(
            session_id=self.session_id,
            order_id=intent.order.order_id,
            fill_seq=self._fill_seq,
            symbol=intent.order.symbol,
            quantity=qty,
            price=fill_price,
        )
        if fill_id in self._applied_fill_ids:
            intent.transition(PaperOrderStatus.REJECTED, reason="duplicate_fill_id")
            return ExecutionResult(intent, None, True, reason="duplicate_fill_id")

        fill = build_fill(
            fill_id=fill_id,
            order_id=intent.order.order_id,
            timestamp=execution_time,
            symbol=intent.order.symbol,
            side=intent.order.side,
            quantity=qty,
            price=fill_price,
            slippage_per_unit=slip,
            transaction_cost=costs.total,
        )
        self._applied_fill_ids.add(fill_id)
        intent.filled_quantity += qty
        if intent.remaining_quantity <= 1e-9:
            intent.transition(PaperOrderStatus.FILLED)
        else:
            if self.fill_config.partial_fill_policy == PartialFillPolicy.ALL_OR_NOTHING:
                # Should not happen; fail closed
                intent.transition(PaperOrderStatus.REJECTED, reason="partial_unexpected")
                return ExecutionResult(intent, None, True, reason="partial_unexpected")
            if intent.status != PaperOrderStatus.PARTIALLY_FILLED:
                intent.transition(PaperOrderStatus.PARTIALLY_FILLED)

        return ExecutionResult(intent, fill, False, reason=None)
