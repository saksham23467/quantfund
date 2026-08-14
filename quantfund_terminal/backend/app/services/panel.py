"""Shared, cached demo market panel (synthetic, clearly labelled)."""

from __future__ import annotations

from functools import lru_cache

from quantfund_terminal.analytics_engine.sample_data import MarketPanel, make_demo_panel


@lru_cache(maxsize=1)
def get_panel() -> MarketPanel:
    return make_demo_panel()
