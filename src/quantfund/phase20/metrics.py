"""Daily / session metrics for Phase 20 paper validation."""

from __future__ import annotations

import math
from typing import Any

from quantfund.trading.models import Fill


def _safe_div(a: float, b: float) -> float | None:
    if b == 0:
        return None
    return a / b


def sharpe_from_returns(returns: list[float], *, periods_per_year: float = 252.0) -> float | None:
    if len(returns) < 2:
        return None
    mu = sum(returns) / len(returns)
    var = sum((r - mu) ** 2 for r in returns) / (len(returns) - 1)
    if var <= 0:
        return None
    return (mu / math.sqrt(var)) * math.sqrt(periods_per_year)


def max_drawdown(equity_curve: list[float]) -> float | None:
    if not equity_curve:
        return None
    peak = equity_curve[0]
    dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            dd = max(dd, (peak - eq) / peak)
    return dd


def trade_pnls_from_fills(fills: list[Fill]) -> list[float]:
    """Pair buy→sell round-trips approximately by symbol FIFO."""
    lots: dict[str, list[tuple[float, float]]] = {}
    pnls: list[float] = []
    for f in fills:
        side = getattr(f, "side", None)
        side_v = side.value if hasattr(side, "value") else str(side or "").upper()
        qty = float(f.quantity)
        px = float(f.price)
        fees = float(getattr(f, "transaction_cost", 0.0) or 0.0)
        slip = float(getattr(f, "slippage_per_unit", 0.0) or 0.0) * qty
        if side_v in {"BUY", "OrderSide.BUY"} or (hasattr(side, "name") and side.name == "BUY"):
            lots.setdefault(f.symbol, []).append((qty, px + (fees + slip) / max(qty, 1e-9)))
        else:
            remaining = qty
            book = lots.setdefault(f.symbol, [])
            proceeds = px * qty - fees - slip
            cost = 0.0
            sold = 0.0
            while remaining > 1e-12 and book:
                lq, lpx = book[0]
                take = min(lq, remaining)
                cost += take * lpx
                sold += take
                lq -= take
                remaining -= take
                if lq <= 1e-12:
                    book.pop(0)
                else:
                    book[0] = (lq, lpx)
            if sold > 0:
                pnls.append(proceeds * (sold / qty) - cost if qty else -cost)
    return pnls


def daily_metrics(
    *,
    day_index: int,
    equity: float,
    prior_equity: float,
    fills_today: list[Fill],
    risk_rejections: int,
    stale_events: int,
    bars_rejected: int,
    latency_seconds: float | None,
    exposure: float,
    signal_count: int,
    cumulative_turnover: float,
) -> dict[str, Any]:
    day_pnl = equity - prior_equity
    day_ret = _safe_div(day_pnl, prior_equity) if prior_equity else None
    trade_pnls = trade_pnls_from_fills(fills_today)
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    return {
        "day_index": day_index,
        "pnl": day_pnl,
        "return": day_ret,
        "equity": equity,
        "drawdown": None,  # filled at session level
        "sharpe": None,  # filled at session level
        "turnover": sum(abs(f.quantity * f.price) for f in fills_today),
        "cumulative_turnover": cumulative_turnover,
        "trade_count": len(fills_today),
        "win_rate": _safe_div(len(wins), len(trade_pnls)) if trade_pnls else None,
        "average_trade": (sum(trade_pnls) / len(trade_pnls)) if trade_pnls else None,
        "maximum_loss": min(trade_pnls) if trade_pnls else None,
        "exposure": exposure,
        "slippage": sum(float(getattr(f, "slippage_per_unit", 0.0) or 0.0) * f.quantity for f in fills_today),
        "signal_frequency": signal_count,
        "risk_rejections": risk_rejections,
        "data_quality_events": bars_rejected + stale_events,
        "latency_seconds": latency_seconds,
        "stale_events": stale_events,
    }


def session_metrics(
    *,
    daily: list[dict[str, Any]],
    equity_curve: list[float],
    all_fills: list[Fill],
    initial_cash: float,
) -> dict[str, Any]:
    returns = [d["return"] for d in daily if d.get("return") is not None]
    pnls = trade_pnls_from_fills(all_fills)
    wins = [p for p in pnls if p > 0]
    total_pnl = (equity_curve[-1] - initial_cash) if equity_curve else 0.0
    return {
        "trading_days": len(daily),
        "total_pnl": total_pnl,
        "total_return": _safe_div(total_pnl, initial_cash),
        "max_drawdown": max_drawdown(equity_curve),
        "sharpe": sharpe_from_returns([float(r) for r in returns if r is not None]),
        "turnover": sum(float(d.get("turnover") or 0) for d in daily),
        "trade_count": len(all_fills),
        "closed_trades": len(pnls),
        "win_rate": _safe_div(len(wins), len(pnls)) if pnls else None,
        "average_trade": (sum(pnls) / len(pnls)) if pnls else None,
        "maximum_loss": min(pnls) if pnls else None,
        "exposure_end": daily[-1]["exposure"] if daily else 0.0,
        "slippage": sum(float(d.get("slippage") or 0) for d in daily),
        "signal_frequency": sum(int(d.get("signal_frequency") or 0) for d in daily),
        "risk_rejections": sum(int(d.get("risk_rejections") or 0) for d in daily),
        "data_quality_events": sum(int(d.get("data_quality_events") or 0) for d in daily),
        "avg_latency_seconds": (
            sum(float(d["latency_seconds"]) for d in daily if d.get("latency_seconds") is not None)
            / max(1, sum(1 for d in daily if d.get("latency_seconds") is not None))
            if any(d.get("latency_seconds") is not None for d in daily)
            else None
        ),
        "per_trade_pnl": pnls,
    }
