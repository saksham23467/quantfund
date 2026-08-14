"""Vectorized, long-only cross-sectional backtester for the demo.

Supports the five strategy families the Research Lab exposes. It models explicit
transaction costs and slippage and uses next-bar execution (signals computed on
close t, positions held from t+1) to avoid look-ahead. Results inherit the input
dataset's data_class; on DEMO_SYNTHETIC data they are illustrative only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from quantfund_terminal.analytics_engine.metrics import (
    PerformanceSummary,
    summarize_returns,
    to_equity_curve,
)

Family = Literal["momentum", "trend", "mean_reversion", "breakout", "volatility"]


@dataclass
class BacktestConfig:
    family: Family = "momentum"
    lookback: int = 126
    holding_top_n: int = 5
    rebalance_days: int = 21
    cost_bps: float = 10.0  # per-side transaction cost
    slippage_bps: float = 5.0  # per-side slippage
    start: str | None = None
    end: str | None = None


@dataclass
class BacktestResult:
    summary: PerformanceSummary
    equity_curve: list[dict]
    drawdown_curve: list[dict]
    config: dict
    data_class: str
    n_symbols: int
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "summary": self.summary.as_dict(),
            "equity_curve": self.equity_curve,
            "drawdown_curve": self.drawdown_curve,
            "config": self.config,
            "data_class": self.data_class,
            "n_symbols": self.n_symbols,
            "warnings": self.warnings,
        }


def _raw_signal(prices: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    rets = prices.pct_change()
    if cfg.family == "momentum":
        return prices.pct_change(cfg.lookback)
    if cfg.family == "trend":
        fast = prices.rolling(max(2, cfg.lookback // 4)).mean()
        slow = prices.rolling(cfg.lookback).mean()
        return (fast - slow) / slow
    if cfg.family == "mean_reversion":
        # Contrarian: negative of recent return (z-scored).
        z = (rets.rolling(cfg.lookback).mean()) / (rets.rolling(cfg.lookback).std())
        return -z
    if cfg.family == "breakout":
        high = prices.rolling(cfg.lookback).max()
        return prices / high - 1.0
    if cfg.family == "volatility":
        # Low-volatility preference: rank by inverse realized vol.
        vol = rets.rolling(cfg.lookback).std()
        return -vol
    raise ValueError(f"unknown family {cfg.family!r}")


def _target_weights(signal: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    weights = pd.DataFrame(0.0, index=signal.index, columns=signal.columns)
    top_n = max(1, cfg.holding_top_n)
    rebalance_idx = signal.index[:: max(1, cfg.rebalance_days)]
    for dt in rebalance_idx:
        row = signal.loc[dt].dropna()
        if row.empty:
            continue
        winners = row.nlargest(top_n).index
        weights.loc[dt, winners] = 1.0 / len(winners)
    # Hold weights between rebalances.
    weights = weights.replace(0.0, np.nan)
    weights = weights.ffill().fillna(0.0)
    # Zero out names not currently selected (ffill keeps last non-nan per column,
    # so re-apply the rebalance mask forward).
    active = pd.DataFrame(False, index=signal.index, columns=signal.columns)
    current: set[str] = set()
    for dt in signal.index:
        if dt in set(rebalance_idx):
            row = signal.loc[dt].dropna()
            current = set(row.nlargest(top_n).index) if not row.empty else current
        for c in current:
            active.loc[dt, c] = True
    weights = weights.where(active, 0.0)
    # Renormalize.
    row_sums = weights.sum(axis=1).replace(0.0, np.nan)
    weights = weights.div(row_sums, axis=0).fillna(0.0)
    return weights


def run_backtest(prices: pd.DataFrame, cfg: BacktestConfig, *, data_class: str) -> BacktestResult:
    warnings: list[str] = []
    if cfg.start:
        prices = prices.loc[prices.index >= pd.Timestamp(cfg.start)]
    if cfg.end:
        prices = prices.loc[prices.index <= pd.Timestamp(cfg.end)]
    if prices.shape[0] <= cfg.lookback + 2:
        warnings.append("insufficient_history_for_lookback")

    signal = _raw_signal(prices, cfg)
    weights = _target_weights(signal, cfg)

    asset_returns = prices.pct_change().fillna(0.0)
    # Next-bar execution: yesterday's target weights earn today's return.
    held = weights.shift(1).fillna(0.0)
    gross = (held * asset_returns).sum(axis=1)

    # Costs + slippage on traded notional (per-side, both legs).
    traded = held.diff().abs().sum(axis=1).fillna(0.0)
    cost_rate = (cfg.cost_bps + cfg.slippage_bps) / 1e4
    net = gross - traded * cost_rate

    summary = summarize_returns(net, trade_returns=net[net != 0.0], weights=held)
    equity = to_equity_curve(net)
    dd = equity / equity.cummax() - 1.0

    return BacktestResult(
        summary=summary,
        equity_curve=[
            {"date": d.strftime("%Y-%m-%d"), "equity": round(float(v), 5)}
            for d, v in equity.items()
        ],
        drawdown_curve=[
            {"date": d.strftime("%Y-%m-%d"), "drawdown": round(float(v), 5)}
            for d, v in dd.items()
        ],
        config=cfg.__dict__,
        data_class=data_class,
        n_symbols=prices.shape[1],
        warnings=warnings,
    )
