"""Paper performance observation stats — not automatic acceptance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quantfund.trading.models import Fill, OrderSide


@dataclass
class PaperPerformanceStats:
    sessions: int
    trades: int
    win_rate: float | None
    average_win: float | None
    average_loss: float | None
    turnover: float
    costs: float
    slippage: float
    drawdown: float | None
    note: str = "Paper profitability ≠ strategy acceptance."

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": self.sessions,
            "trades": self.trades,
            "win_rate": self.win_rate,
            "average_win": self.average_win,
            "average_loss": self.average_loss,
            "turnover": self.turnover,
            "costs": self.costs,
            "slippage": self.slippage,
            "drawdown": self.drawdown,
            "note": self.note,
            "auto_accepted": False,
        }


def summarize_fills(fills: list[Fill], *, sessions: int = 1) -> PaperPerformanceStats:
    turnover = sum(f.quantity * f.price for f in fills)
    costs = sum(f.transaction_cost for f in fills)
    slip = sum(abs(f.slippage_per_unit) * f.quantity for f in fills)
    # Simplified round-trip PnL proxy unavailable without marks — report None win stats
    return PaperPerformanceStats(
        sessions=sessions,
        trades=len(fills),
        win_rate=None,
        average_win=None,
        average_loss=None,
        turnover=turnover,
        costs=costs,
        slippage=slip,
        drawdown=None,
    )
