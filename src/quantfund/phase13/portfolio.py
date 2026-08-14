"""Paper portfolio accounting helpers + CA updates (RAW OHLC untouched)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.paper.portfolio import PaperPortfolio
from quantfund.trading.models import Fill


@dataclass
class PortfolioAccountingSnapshot:
    cash: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    gross_exposure: float
    net_exposure: float
    turnover: float
    fees: float
    slippage: float
    positions: dict[str, dict[str, float]]
    max_drawdown: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash": self.cash,
            "equity": self.equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "gross_exposure": self.gross_exposure,
            "net_exposure": self.net_exposure,
            "turnover": self.turnover,
            "fees": self.fees,
            "slippage": self.slippage,
            "positions": self.positions,
            "max_drawdown": self.max_drawdown,
        }


@dataclass
class CAApplicationResult:
    applied: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers


def snapshot_accounting(
    book: PaperPortfolio,
    *,
    fills: list[Fill],
    equity_curve: list[float] | None = None,
) -> PortfolioAccountingSnapshot:
    snap = book.snapshot()
    turnover = sum(abs(f.quantity * f.price) for f in fills)
    curve = equity_curve or []
    max_dd: float | None = None
    if curve:
        peak = curve[0]
        max_dd = 0.0
        for eq in curve:
            peak = max(peak, eq)
            if peak > 0:
                max_dd = max(max_dd, (peak - eq) / peak)
    positions = {
        sym: {
            "quantity": float(meta["quantity"]),
            "average_entry_price": float(meta["average_entry_price"]),
        }
        for sym, meta in (snap.get("positions") or {}).items()
    }
    exposure = float(snap.get("equity", 0.0) - snap.get("cash", 0.0))
    return PortfolioAccountingSnapshot(
        cash=float(snap["cash"]),
        equity=float(snap["equity"]),
        realized_pnl=float(snap.get("realized_pnl", 0.0)),
        unrealized_pnl=float(snap.get("unrealized_pnl", 0.0)),
        gross_exposure=abs(exposure),
        net_exposure=exposure,
        turnover=turnover,
        fees=float(snap.get("total_transaction_costs", 0.0)),
        slippage=float(snap.get("total_slippage", 0.0)),
        positions=positions,
        max_drawdown=max_dd,
    )


def apply_corporate_actions_to_book(
    book: PaperPortfolio,
    actions: list[CorporateAction],
    *,
    as_of: date,
) -> CAApplicationResult:
    """Apply split/bonus quantity and dividend cash; mergers/demergers stay manual."""
    result = CAApplicationResult()
    for ca in sorted(actions, key=lambda a: a.ex_date):
        if ca.ex_date > as_of:
            result.skipped.append(f"future:{ca.action_id}")
            continue
        qty = book.position_quantity(ca.symbol)
        if ca.action_type in {CorporateActionType.MERGER, CorporateActionType.DEMERGER}:
            result.skipped.append(f"manual_unsupported:{ca.action_id}")
            continue
        if ca.action_type in {CorporateActionType.SPLIT, CorporateActionType.BONUS}:
            factor = ca.split_factor
            if factor is None or factor <= 0:
                result.blockers.append(f"invalid_split_factor:{ca.action_id}")
                continue
            if qty == 0:
                result.skipped.append(f"no_position:{ca.action_id}")
                continue
            # Adjust quantity via portfolio internals carefully
            pos = book.portfolio.positions.get(ca.symbol)
            if pos is None:
                result.skipped.append(f"no_position:{ca.action_id}")
                continue
            new_qty = qty * factor
            # Preserve notional: average entry / factor
            avg = pos.average_entry_price / factor if factor else pos.average_entry_price
            pos.quantity = new_qty
            pos.average_entry_price = avg
            result.applied.append(
                {
                    "action_id": ca.action_id,
                    "type": ca.action_type.value,
                    "symbol": ca.symbol,
                    "factor": factor,
                    "quantity_after": new_qty,
                    "avg_entry_after": avg,
                }
            )
            continue
        if ca.action_type == CorporateActionType.DIVIDEND:
            if qty <= 0 or ca.cash_amount is None:
                result.skipped.append(f"dividend_noop:{ca.action_id}")
                continue
            cash_in = float(qty) * float(ca.cash_amount)
            book.portfolio.cash += cash_in
            result.applied.append(
                {
                    "action_id": ca.action_id,
                    "type": "dividend",
                    "symbol": ca.symbol,
                    "cash_in": cash_in,
                    "cash_after": book.portfolio.cash,
                }
            )
            continue
        result.skipped.append(f"unhandled:{ca.action_id}:{ca.action_type.value}")
    return result
