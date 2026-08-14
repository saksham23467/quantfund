"""Deterministic SYNTHETIC market panel for the investor demo.

IMPORTANT: This is clearly-labelled synthetic data for UI/engine demonstration
only. It is NOT certified, NOT exchange-authoritative, and any metrics derived
from it carry data_class=DEMO_SYNTHETIC. It must never be presented as a
research-eligible backtest result.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DEMO_UNIVERSE = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC",
    "LT", "AXISBANK", "KOTAKBANK", "HINDUNILVR", "BHARTIARTL", "ASIANPAINT",
    "MARUTI", "TITAN", "SUNPHARMA", "WIPRO", "ULTRACEMCO", "NESTLEIND", "BAJFINANCE",
]

SECTOR_MAP = {
    "RELIANCE": "Energy", "TCS": "IT", "INFY": "IT", "WIPRO": "IT",
    "HDFCBANK": "Financials", "ICICIBANK": "Financials", "SBIN": "Financials",
    "AXISBANK": "Financials", "KOTAKBANK": "Financials", "BAJFINANCE": "Financials",
    "ITC": "FMCG", "HINDUNILVR": "FMCG", "NESTLEIND": "FMCG", "TITAN": "Consumer",
    "ASIANPAINT": "Materials", "ULTRACEMCO": "Materials", "LT": "Industrials",
    "BHARTIARTL": "Telecom", "MARUTI": "Auto", "SUNPHARMA": "Pharma",
}


@dataclass
class MarketPanel:
    prices: pd.DataFrame  # index=date, columns=symbol (close)
    volumes: pd.DataFrame
    data_class: str = "DEMO_SYNTHETIC"
    source: str = "synthetic_gbm_seed42"

    @property
    def returns(self) -> pd.DataFrame:
        return self.prices.pct_change().fillna(0.0)


def make_demo_panel(
    *,
    symbols: list[str] | None = None,
    start: str = "2015-01-01",
    end: str = "2026-06-30",
    seed: int = 42,
) -> MarketPanel:
    symbols = symbols or DEMO_UNIVERSE
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, end=end)
    n = len(dates)

    # Per-symbol drift/vol, plus a shared market factor for realistic correlation.
    market = rng.normal(0.0003, 0.010, size=n)
    prices = {}
    volumes = {}
    for i, sym in enumerate(symbols):
        beta = 0.6 + 0.9 * rng.random()
        idio = rng.normal(0.0, 0.012, size=n)
        drift = rng.normal(0.0002, 0.0003)
        daily = drift + beta * market + idio
        px = 100.0 * np.exp(np.cumsum(daily))
        prices[sym] = px
        base_vol = rng.integers(5e5, 5e6)
        volumes[sym] = (base_vol * (1.0 + 0.3 * rng.standard_normal(n))).clip(min=1e4)

    px_df = pd.DataFrame(prices, index=dates).round(2)
    vol_df = pd.DataFrame(volumes, index=dates).round(0)
    return MarketPanel(prices=px_df, volumes=vol_df)
