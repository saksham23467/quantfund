"""Performance metrics computed from a returns series. No look-ahead, no I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def to_equity_curve(returns: pd.Series, *, start_value: float = 1.0) -> pd.Series:
    return (1.0 + returns.fillna(0.0)).cumprod() * start_value


def cagr(returns: pd.Series, *, periods_per_year: int = TRADING_DAYS) -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    equity = float((1.0 + r).prod())
    years = len(r) / periods_per_year
    if years <= 0 or equity <= 0:
        return 0.0
    return equity ** (1.0 / years) - 1.0


def sharpe(returns: pd.Series, *, rf: float = 0.0, periods_per_year: int = TRADING_DAYS) -> float:
    r = returns.dropna() - rf / periods_per_year
    if r.std(ddof=1) == 0 or r.empty:
        return 0.0
    return float(np.sqrt(periods_per_year) * r.mean() / r.std(ddof=1))


def sortino(returns: pd.Series, *, rf: float = 0.0, periods_per_year: int = TRADING_DAYS) -> float:
    r = returns.dropna() - rf / periods_per_year
    downside = r[r < 0]
    dd = downside.std(ddof=1)
    if dd == 0 or np.isnan(dd) or r.empty:
        return 0.0
    return float(np.sqrt(periods_per_year) * r.mean() / dd)


def max_drawdown(returns: pd.Series) -> float:
    equity = to_equity_curve(returns)
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def volatility(returns: pd.Series, *, periods_per_year: int = TRADING_DAYS) -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    return float(r.std(ddof=1) * np.sqrt(periods_per_year))


def win_rate(trade_returns: pd.Series) -> float:
    t = trade_returns.dropna()
    if t.empty:
        return 0.0
    return float((t > 0).mean())


def profit_factor(trade_returns: pd.Series) -> float:
    t = trade_returns.dropna()
    gains = t[t > 0].sum()
    losses = -t[t < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def turnover(weights: pd.DataFrame) -> float:
    """Average one-way turnover per rebalance from a (time x asset) weights frame."""
    if weights is None or weights.empty or len(weights) < 2:
        return 0.0
    return float(weights.diff().abs().sum(axis=1).mean() / 2.0)


def average_exposure(weights: pd.DataFrame) -> float:
    if weights is None or weights.empty:
        return 0.0
    return float(weights.abs().sum(axis=1).mean())


@dataclass
class PerformanceSummary:
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    volatility: float
    win_rate: float
    profit_factor: float
    turnover: float
    exposure: float
    n_periods: int

    def as_dict(self) -> dict:
        return asdict(self)


def summarize_returns(
    returns: pd.Series,
    *,
    trade_returns: pd.Series | None = None,
    weights: pd.DataFrame | None = None,
    periods_per_year: int = TRADING_DAYS,
) -> PerformanceSummary:
    tr = trade_returns if trade_returns is not None else returns
    return PerformanceSummary(
        cagr=round(cagr(returns, periods_per_year=periods_per_year), 6),
        sharpe=round(sharpe(returns, periods_per_year=periods_per_year), 6),
        sortino=round(sortino(returns, periods_per_year=periods_per_year), 6),
        max_drawdown=round(max_drawdown(returns), 6),
        volatility=round(volatility(returns, periods_per_year=periods_per_year), 6),
        win_rate=round(win_rate(tr), 6),
        profit_factor=round(profit_factor(tr), 6),
        turnover=round(turnover(weights), 6) if weights is not None else 0.0,
        exposure=round(average_exposure(weights), 6) if weights is not None else 0.0,
        n_periods=int(returns.dropna().shape[0]),
    )
