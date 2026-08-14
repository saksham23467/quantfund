"""Fail-closed reconciliation between fills, ledgers, and portfolio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.paper.portfolio import PaperPortfolio
from quantfund.trading.models import Fill, OrderSide


@dataclass
class ReconciliationIssue:
    code: str
    message: str


@dataclass
class ReconciliationReport:
    ok: bool
    issues: list[ReconciliationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [{"code": i.code, "message": i.message} for i in self.issues],
        }


def reconcile_paper_state(
    paper: PaperPortfolio,
    *,
    fills: list[Fill],
    initial_cash: float,
    allow_negative_cash: bool = False,
    epsilon: float = 1e-6,
    known_order_ids: set[str] | None = None,
    audit_fill_ids: set[str] | None = None,
) -> ReconciliationReport:
    issues: list[ReconciliationIssue] = []

    fill_ids = [f.fill_id for f in fills]
    if len(fill_ids) != len(set(fill_ids)):
        issues.append(
            ReconciliationIssue("duplicate_fill", "duplicate fill_id in fill list")
        )

    # Position deltas from fills vs ledger
    qty_by_symbol: dict[str, float] = {}
    cash_from_fills = initial_cash
    for f in fills:
        if f.quantity <= 0:
            issues.append(
                ReconciliationIssue(
                    "impossible_quantity",
                    f"fill {f.fill_id} has non-positive quantity",
                )
            )
        delta = f.quantity if f.side == OrderSide.BUY else -f.quantity
        qty_by_symbol[f.symbol] = qty_by_symbol.get(f.symbol, 0.0) + delta
        cash_from_fills += f.net_cash_delta
        if known_order_ids is not None and f.order_id not in known_order_ids:
            issues.append(
                ReconciliationIssue(
                    "orphan_fill",
                    f"fill {f.fill_id} references unknown order {f.order_id}",
                )
            )

    for sym, expected_qty in qty_by_symbol.items():
        actual = paper.position_quantity(sym)
        if abs(actual - expected_qty) > epsilon:
            issues.append(
                ReconciliationIssue(
                    "position_mismatch",
                    f"{sym}: fill_delta={expected_qty} portfolio={actual}",
                )
            )
        if actual < -epsilon:
            issues.append(
                ReconciliationIssue(
                    "negative_holdings",
                    f"{sym}: quantity={actual}",
                )
            )

    if abs(paper.cash_balance - cash_from_fills) > epsilon:
        issues.append(
            ReconciliationIssue(
                "cash_mismatch",
                f"cash portfolio={paper.cash_balance} from_fills={cash_from_fills}",
            )
        )

    if not allow_negative_cash and paper.cash_balance < -epsilon:
        issues.append(
            ReconciliationIssue(
                "negative_cash",
                f"cash={paper.cash_balance} prohibited",
            )
        )

    # Ledger fill ids must match applied set
    ledger_fill_ids = {e.payload["fill_id"] for e in paper.positions.entries}
    if ledger_fill_ids != set(paper.applied_fill_ids):
        issues.append(
            ReconciliationIssue(
                "ledger_fill_set_mismatch",
                "position ledger fill_ids != applied_fill_ids",
            )
        )

    if audit_fill_ids is not None:
        missing = set(fill_ids) - audit_fill_ids
        extra = audit_fill_ids - set(fill_ids)
        if missing:
            issues.append(
                ReconciliationIssue(
                    "missing_fills_in_audit",
                    f"fills missing from audit: {sorted(missing)[:5]}",
                )
            )
        if extra:
            issues.append(
                ReconciliationIssue(
                    "orphan_audit_fills",
                    f"audit fills not in ledger: {sorted(extra)[:5]}",
                )
            )

    # Equity identity
    mv = paper.portfolio.total_market_value()
    if abs(paper.equity() - (paper.cash_balance + mv)) > epsilon:
        issues.append(
            ReconciliationIssue(
                "equity_identity",
                "equity != cash + market_value",
            )
        )

    return ReconciliationReport(ok=len(issues) == 0, issues=issues)
