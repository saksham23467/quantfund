"""In-memory strategy draft store for the demo (non-persistent).

In production this is backed by Postgres (see docs/DATABASE_SCHEMA.md). Drafts
are never auto-run and never accepted without a research-eligible dataset.
"""

from __future__ import annotations

import itertools

_ID = itertools.count(1)
_STRATEGIES: list[dict] = []

VALID_FAMILIES = {"momentum", "trend", "mean_reversion", "breakout", "volatility"}


def create_strategy(name: str, family: str, params: dict) -> dict:
    fam = family if family in VALID_FAMILIES else "momentum"
    strat = {
        "id": next(_ID),
        "name": name,
        "family": fam,
        "params": params or {},
        "status": "DRAFT",
        "note": "Draft only. Backtest is gated by dataset certification.",
    }
    _STRATEGIES.append(strat)
    return strat


def list_strategies() -> list[dict]:
    return list(_STRATEGIES)
