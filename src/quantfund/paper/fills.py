"""Paper fill policy helpers. Fill objects are created only by PaperExecutionAdapter."""

from __future__ import annotations

from dataclasses import dataclass

from quantfund.paper.models import PartialFillPolicy, deterministic_id
from quantfund.trading.models import Fill, OrderSide


@dataclass(frozen=True)
class PaperFillConfig:
    partial_fill_policy: PartialFillPolicy = PartialFillPolicy.ALL_OR_NOTHING
    partial_fill_ratio: float = 1.0
    reject_on_insufficient_cash: bool = True
    reject_on_insufficient_position: bool = True
    reject_on_market_closed: bool = True
    reject_on_stale_data: bool = True


def compute_fill_quantity(
    *,
    remaining_quantity: float,
    policy: PartialFillPolicy,
    ratio: float,
) -> float:
    if remaining_quantity <= 0:
        return 0.0
    if policy == PartialFillPolicy.ALL_OR_NOTHING:
        return remaining_quantity
    return max(0.0, min(remaining_quantity, remaining_quantity * ratio))


def make_fill_id(
    *,
    session_id: str,
    order_id: str,
    fill_seq: int,
    symbol: str,
    quantity: float,
    price: float,
) -> str:
    return deterministic_id(
        "fill",
        session_id,
        order_id,
        fill_seq,
        symbol,
        f"{quantity:.8f}",
        f"{price:.8f}",
    )


def build_fill(
    *,
    fill_id: str,
    order_id: str,
    timestamp,
    symbol: str,
    side: OrderSide,
    quantity: float,
    price: float,
    slippage_per_unit: float,
    transaction_cost: float,
) -> Fill:
    """Construct trading.Fill with deterministic fill_id (paper factory only)."""
    gross = quantity * price
    if side == OrderSide.BUY:
        net_cash = -(gross + transaction_cost)
    else:
        net_cash = gross - transaction_cost
    return Fill(
        fill_id=fill_id,
        order_id=order_id,
        timestamp=timestamp,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        slippage_per_unit=slippage_per_unit,
        transaction_cost=transaction_cost,
        gross_value=gross,
        net_cash_delta=net_cash,
    )
