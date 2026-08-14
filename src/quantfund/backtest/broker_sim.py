"""Simulated broker: slippage, costs, and Fill creation.

Only this component may create Fill objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from quantfund.backtest.costs import CostModel, EquityDeliveryCostModel, MarketSegment
from quantfund.trading.models import Fill, Order, OrderSide, OrderStatus


@dataclass(frozen=True)
class SlippageModel:
    """Fixed fractional slippage applied adversely to the taker.

    ``bps`` is basis points of the reference price (100 bps = 1%).
    Research assumption — not a calibrated market-impact model.
    """

    bps: float = 5.0

    @property
    def name(self) -> str:
        return f"fixed_bps_{self.bps:g}"

    def apply(self, *, side: OrderSide, price: float) -> tuple[float, float]:
        """Return (fill_price, slippage_per_unit)."""
        slip = price * (self.bps / 10_000.0)
        if side == OrderSide.BUY:
            return price + slip, slip
        return price - slip, -slip


class BrokerSimulator:
    """Paper/backtest execution venue. Creates fills; never talks to a real broker."""

    def __init__(
        self,
        cost_model: CostModel | None = None,
        slippage_model: SlippageModel | None = None,
    ) -> None:
        self.cost_model = cost_model or EquityDeliveryCostModel()
        self.slippage_model = slippage_model or SlippageModel()

    def execute(
        self,
        order: Order,
        *,
        execution_time: datetime,
        open_price: float,
    ) -> Fill:
        """Execute a scheduled order at next-bar open with slippage and costs."""
        if order.status not in {OrderStatus.ACCEPTED, OrderStatus.SCHEDULED}:
            raise ValueError(f"cannot execute order in status {order.status}")
        if open_price <= 0:
            raise ValueError("open_price must be positive")

        fill_price, slip_per_unit = self.slippage_model.apply(
            side=order.side, price=open_price
        )
        costs = self.cost_model.compute(
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            segment=MarketSegment.EQUITY_DELIVERY,
        )
        gross = order.quantity * fill_price
        if order.side == OrderSide.BUY:
            net_cash = -(gross + costs.total)
        else:
            net_cash = gross - costs.total

        order.status = OrderStatus.FILLED
        return Fill(
            order_id=order.order_id,
            timestamp=execution_time,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            slippage_per_unit=slip_per_unit,
            transaction_cost=costs.total,
            gross_value=gross,
            net_cash_delta=net_cash,
        )
