"""Paper position/cash ledgers materializing into existing Portfolio accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from quantfund.backtest.portfolio import Portfolio
from quantfund.trading.models import Fill, OrderSide


@dataclass
class LedgerEntry:
    seq: int
    timestamp: datetime
    kind: str
    payload: dict[str, Any]


@dataclass
class PositionLedger:
    entries: list[LedgerEntry] = field(default_factory=list)
    _seq: int = 0

    def append(
        self,
        *,
        timestamp: datetime,
        symbol: str,
        delta_qty: float,
        fill_id: str,
        quantity_after: float,
    ) -> LedgerEntry:
        self._seq += 1
        entry = LedgerEntry(
            seq=self._seq,
            timestamp=timestamp,
            kind="position_changed",
            payload={
                "symbol": symbol,
                "delta_qty": delta_qty,
                "fill_id": fill_id,
                "quantity_after": quantity_after,
            },
        )
        self.entries.append(entry)
        return entry


@dataclass
class CashLedger:
    entries: list[LedgerEntry] = field(default_factory=list)
    _seq: int = 0

    def append(
        self,
        *,
        timestamp: datetime,
        delta_cash: float,
        fill_id: str,
        cash_after: float,
    ) -> LedgerEntry:
        self._seq += 1
        entry = LedgerEntry(
            seq=self._seq,
            timestamp=timestamp,
            kind="cash_changed",
            payload={
                "delta_cash": delta_cash,
                "fill_id": fill_id,
                "cash_after": cash_after,
            },
        )
        self.entries.append(entry)
        return entry


@dataclass
class PaperPortfolio:
    """Event-sourced ledgers + Portfolio materialization (reuse Portfolio math)."""

    portfolio: Portfolio
    positions: PositionLedger = field(default_factory=PositionLedger)
    cash: CashLedger = field(default_factory=CashLedger)
    applied_fill_ids: set[str] = field(default_factory=set)

    @classmethod
    def create(cls, initial_cash: float) -> PaperPortfolio:
        return cls(portfolio=Portfolio(cash=initial_cash))

    @property
    def cash_balance(self) -> float:
        return self.portfolio.cash

    def position_quantity(self, symbol: str) -> float:
        return self.portfolio.position_quantity(symbol)

    def exposure(self) -> float:
        return self.portfolio.exposure()

    def equity(self) -> float:
        return self.portfolio.equity

    def realized_pnl(self) -> float:
        return self.portfolio.realized_pnl

    def unrealized_pnl(self) -> float:
        return self.portfolio.unrealized_pnl()

    def update_mark(self, symbol: str, price: float) -> None:
        self.portfolio.update_mark(symbol, price)

    def apply_fill(self, fill: Fill) -> list[LedgerEntry]:
        if fill.fill_id in self.applied_fill_ids:
            raise ValueError(f"duplicate_fill_application:{fill.fill_id}")
        before_qty = self.position_quantity(fill.symbol)
        self.portfolio.apply_fill(fill)
        self.applied_fill_ids.add(fill.fill_id)
        after_qty = self.position_quantity(fill.symbol)
        delta = after_qty - before_qty
        # For sells delta is negative; for buys positive
        if fill.side == OrderSide.SELL and delta > 0:
            raise ValueError("impossible_position_delta_on_sell")
        pe = self.positions.append(
            timestamp=fill.timestamp,
            symbol=fill.symbol,
            delta_qty=delta,
            fill_id=fill.fill_id,
            quantity_after=after_qty,
        )
        ce = self.cash.append(
            timestamp=fill.timestamp,
            delta_cash=fill.net_cash_delta,
            fill_id=fill.fill_id,
            cash_after=self.portfolio.cash,
        )
        return [pe, ce]

    def snapshot(self) -> dict[str, Any]:
        return {
            "cash": self.portfolio.cash,
            "realized_pnl": self.portfolio.realized_pnl,
            "unrealized_pnl": self.portfolio.unrealized_pnl(),
            "equity": self.portfolio.equity,
            "positions": {
                sym: {
                    "quantity": pos.quantity,
                    "average_entry_price": pos.average_entry_price,
                }
                for sym, pos in sorted(self.portfolio.positions.items())
            },
            "marks": dict(sorted(self.portfolio.marks.items())),
            "fill_ids": sorted(self.applied_fill_ids),
            "total_transaction_costs": self.portfolio.total_transaction_costs,
            "total_slippage": self.portfolio.total_slippage,
        }
