"""Portfolio accounting: cash, positions, realized/unrealized P&L, equity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quantfund.trading.models import Fill, OrderSide, Position


@dataclass
class EquityPoint:
    timestamp: datetime
    cash: float
    market_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float


@dataclass
class Portfolio:
    """Long-only portfolio for Milestone 1. Short selling is not supported."""

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    total_transaction_costs: float = 0.0
    total_slippage: float = 0.0
    equity_curve: list[EquityPoint] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    marks: dict[str, float] = field(default_factory=dict)

    def position_quantity(self, symbol: str) -> float:
        pos = self.positions.get(symbol)
        return pos.quantity if pos else 0.0

    def position_market_value(self, symbol: str, price: float) -> float:
        return self.position_quantity(symbol) * price

    def total_market_value(self) -> float:
        return sum(
            pos.quantity * self.marks.get(pos.symbol, pos.average_entry_price)
            for pos in self.positions.values()
        )

    def unrealized_pnl(self) -> float:
        total = 0.0
        for pos in self.positions.values():
            if pos.quantity == 0:
                continue
            mark = self.marks.get(pos.symbol, pos.average_entry_price)
            total += (mark - pos.average_entry_price) * pos.quantity
        return total

    @property
    def equity(self) -> float:
        return self.cash + self.total_market_value()

    def update_mark(self, symbol: str, price: float) -> None:
        self.marks[symbol] = price

    def apply_fill(self, fill: Fill) -> None:
        """Update cash and positions from a simulator-created fill."""
        self.fills.append(fill)
        self.total_transaction_costs += fill.transaction_cost
        self.total_slippage += abs(fill.slippage_per_unit) * fill.quantity

        pos = self.positions.get(fill.symbol) or Position(symbol=fill.symbol)
        if fill.side == OrderSide.BUY:
            new_qty = pos.quantity + fill.quantity
            if new_qty <= 0:
                raise ValueError("invalid buy resulting quantity")
            if pos.quantity == 0:
                avg = fill.price
            else:
                avg = (
                    (pos.average_entry_price * pos.quantity) + (fill.price * fill.quantity)
                ) / new_qty
            pos.quantity = new_qty
            pos.average_entry_price = avg
            self.cash += fill.net_cash_delta  # negative for buys
        else:
            if fill.quantity > pos.quantity + 1e-9:
                raise ValueError("short selling is not supported in Milestone 1")
            # Realized P&L uses average entry vs fill price, costs already in cash.
            self.realized_pnl += (fill.price - pos.average_entry_price) * fill.quantity
            pos.quantity -= fill.quantity
            self.cash += fill.net_cash_delta  # positive for sells, net of costs
            if pos.quantity == 0:
                pos.average_entry_price = 0.0

        self.positions[fill.symbol] = pos
        self.marks[fill.symbol] = fill.price

    def record_equity(self, timestamp: datetime) -> EquityPoint:
        point = EquityPoint(
            timestamp=timestamp,
            cash=self.cash,
            market_value=self.total_market_value(),
            equity=self.equity,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl(),
        )
        self.equity_curve.append(point)
        return point

    def exposure(self) -> float:
        return self.total_market_value()
