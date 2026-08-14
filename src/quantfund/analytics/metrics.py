"""Backtest performance metrics with explicit edge-case handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from quantfund.backtest.engine import BacktestResult
from quantfund.trading.models import OrderSide


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class PerformanceMetrics:
    total_return: float | None
    cagr: float | None
    annualized_volatility: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    maximum_drawdown: float | None
    calmar_ratio: float | None
    win_rate: float | None
    average_win: float | None
    average_loss: float | None
    profit_factor: float | None
    number_of_trades: int
    turnover: float
    total_transaction_costs: float
    total_slippage: float
    notes: tuple[str, ...] = ()


def _equity_series(result: BacktestResult) -> tuple[np.ndarray, list[datetime]]:
    curve = result.portfolio.equity_curve
    if not curve:
        return np.array([]), []
    values = np.array([p.equity for p in curve], dtype=float)
    times = [p.timestamp for p in curve]
    return values, times


def _max_drawdown(equity: np.ndarray) -> float | None:
    if equity.size == 0:
        return None
    peaks = np.maximum.accumulate(equity)
    # Avoid division by zero if peak is 0 (should not happen with positive capital).
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peaks > 0, (equity - peaks) / peaks, 0.0)
    return float(dd.min())


def _trade_pnls(result: BacktestResult) -> list[float]:
    """Approximate round-trip trade PnLs from sells using average-entry accounting.

    For M1 buy-and-hold, sells may be zero; metrics handle zero-trade cases.
    Each SELL fill contributes (fill.price - avg_entry_at_sale) * qty, but avg
    entry is internal. We use realized_pnl increments by reconstructing from
    fills chronologically.
    """
    avg: dict[str, float] = {}
    qty: dict[str, float] = {}
    pnls: list[float] = []
    for fill in result.portfolio.fills:
        if fill.side == OrderSide.BUY:
            q0 = qty.get(fill.symbol, 0.0)
            if q0 <= 0:
                avg[fill.symbol] = fill.price
            else:
                avg[fill.symbol] = (avg[fill.symbol] * q0 + fill.price * fill.quantity) / (
                    q0 + fill.quantity
                )
            qty[fill.symbol] = q0 + fill.quantity
        else:
            entry = avg.get(fill.symbol, fill.price)
            pnls.append((fill.price - entry) * fill.quantity - fill.transaction_cost)
            qty[fill.symbol] = qty.get(fill.symbol, 0.0) - fill.quantity
            if qty[fill.symbol] <= 1e-12:
                qty[fill.symbol] = 0.0
                avg[fill.symbol] = 0.0
    return pnls


def compute_metrics(result: BacktestResult, *, risk_free_rate: float = 0.0) -> PerformanceMetrics:
    """Compute performance statistics from a BacktestResult.

    Edge cases:
    - zero trades → trade stats are None / 0 as appropriate
    - zero volatility → Sharpe/Sortino are None
    - insufficient history (< 2 equity points) → return metrics None where needed
    - zero drawdown → Calmar is None (undefined / infinite)
    """
    notes: list[str] = []
    equity, times = _equity_series(result)
    initial = result.initial_capital
    final = result.portfolio.equity

    number_of_trades = len(result.portfolio.fills)
    turnover = float(
        sum(f.gross_value for f in result.portfolio.fills) / initial if initial else 0.0
    )

    if equity.size < 1:
        notes.append("insufficient_history")
        return PerformanceMetrics(
            total_return=None,
            cagr=None,
            annualized_volatility=None,
            sharpe_ratio=None,
            sortino_ratio=None,
            maximum_drawdown=None,
            calmar_ratio=None,
            win_rate=None,
            average_win=None,
            average_loss=None,
            profit_factor=None,
            number_of_trades=number_of_trades,
            turnover=turnover,
            total_transaction_costs=result.portfolio.total_transaction_costs,
            total_slippage=result.portfolio.total_slippage,
            notes=tuple(notes),
        )

    total_return = (final / initial) - 1.0 if initial > 0 else None

    # CAGR from calendar span of equity curve
    cagr: float | None = None
    if times and total_return is not None:
        days = (times[-1] - times[0]).total_seconds() / 86400.0
        if days <= 0:
            notes.append("insufficient_history_for_cagr")
        else:
            years = days / 365.25
            if years > 0 and final > 0 and initial > 0:
                cagr = (final / initial) ** (1.0 / years) - 1.0
            else:
                notes.append("cagr_undefined")

    ann_vol: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    if equity.size >= 2:
        rets = np.diff(equity) / equity[:-1]
        # Guard against zeros in equity
        if not np.isfinite(rets).all():
            notes.append("non_finite_returns")
            rets = rets[np.isfinite(rets)]
        if rets.size >= 1:
            vol = float(np.std(rets, ddof=1)) if rets.size >= 2 else 0.0
            if vol == 0.0:
                notes.append("zero_volatility")
                ann_vol = 0.0
            else:
                ann_vol = vol * np.sqrt(TRADING_DAYS_PER_YEAR)
                mean = float(np.mean(rets))
                excess = mean - (risk_free_rate / TRADING_DAYS_PER_YEAR)
                sharpe = (excess / vol) * np.sqrt(TRADING_DAYS_PER_YEAR)
                downside = rets[rets < 0]
                if downside.size == 0:
                    notes.append("no_downside_returns")
                    sortino = None
                else:
                    dvol = float(np.std(downside, ddof=1)) if downside.size >= 2 else 0.0
                    if dvol == 0.0:
                        notes.append("zero_downside_volatility")
                        sortino = None
                    else:
                        sortino = (excess / dvol) * np.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        notes.append("insufficient_history_for_volatility")

    mdd = _max_drawdown(equity)
    calmar: float | None = None
    if mdd is None:
        pass
    elif abs(mdd) < 1e-15:
        notes.append("zero_drawdown")
        calmar = None
    elif cagr is not None:
        calmar = cagr / abs(mdd)

    trade_pnls = _trade_pnls(result)
    if not trade_pnls:
        if number_of_trades == 0:
            notes.append("zero_trades")
        else:
            notes.append("no_closed_round_trips")
        win_rate = None
        average_win = None
        average_loss = None
        profit_factor = None
    else:
        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p < 0]
        win_rate = len(wins) / len(trade_pnls)
        average_win = float(np.mean(wins)) if wins else None
        average_loss = float(np.mean(losses)) if losses else None
        gross_wins = sum(wins)
        gross_losses = -sum(losses)
        if gross_losses == 0:
            profit_factor = None
            notes.append("profit_factor_undefined_no_losses")
        else:
            profit_factor = gross_wins / gross_losses

    return PerformanceMetrics(
        total_return=total_return,
        cagr=cagr,
        annualized_volatility=ann_vol,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        maximum_drawdown=mdd,
        calmar_ratio=calmar,
        win_rate=win_rate,
        average_win=average_win,
        average_loss=average_loss,
        profit_factor=profit_factor,
        number_of_trades=number_of_trades,
        turnover=turnover,
        total_transaction_costs=result.portfolio.total_transaction_costs,
        total_slippage=result.portfolio.total_slippage,
        notes=tuple(notes),
    )
