"""Strategy-family definitions for controlled Phase 19 strategy research.

Families are declarative *specifications* only: a family id, its parameter grid,
and the data requirements it depends on. They contain NO execution logic and
NO acceptance logic (generators must never self-accept). Turning a family +
parameter combination into measured metrics is the job of an injected evaluator
that MUST honour point-in-time universe, RAW execution prices, explicit
transaction costs, explicit slippage, and realistic execution timing.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StrategyFamily(str, Enum):
    TREND_FOLLOWING = "trend_following"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    VOLATILITY_REGIME = "volatility_regime"


@dataclass(frozen=True)
class FamilySpec:
    family: StrategyFamily
    description: str
    param_grid: dict[str, list[Any]]

    def enumerate_params(self) -> list[dict[str, Any]]:
        """Cartesian product of the parameter grid (deterministic order)."""
        if not self.param_grid:
            return [{}]
        keys = sorted(self.param_grid)
        combos = itertools.product(*(self.param_grid[k] for k in keys))
        return [dict(zip(keys, values)) for values in combos]


# Declarative family catalogue. Parameter grids are intentionally small and
# fixed so the research budget is bounded and reproducible.
FAMILY_CATALOGUE: dict[StrategyFamily, FamilySpec] = {
    StrategyFamily.TREND_FOLLOWING: FamilySpec(
        family=StrategyFamily.TREND_FOLLOWING,
        description="Long/short on moving-average trend with a confirmation filter.",
        param_grid={
            "fast_window": [20, 50],
            "slow_window": [100, 200],
        },
    ),
    StrategyFamily.MOMENTUM: FamilySpec(
        family=StrategyFamily.MOMENTUM,
        description="Cross-sectional / time-series momentum over a lookback.",
        param_grid={
            "lookback": [63, 126, 252],
            "holding": [21, 63],
        },
    ),
    StrategyFamily.MEAN_REVERSION: FamilySpec(
        family=StrategyFamily.MEAN_REVERSION,
        description="Revert to a rolling mean when z-score exceeds a band.",
        param_grid={
            "window": [10, 20],
            "entry_z": [1.5, 2.0],
        },
    ),
    StrategyFamily.BREAKOUT: FamilySpec(
        family=StrategyFamily.BREAKOUT,
        description="Channel breakout above/below rolling high/low.",
        param_grid={
            "channel": [20, 55],
            "atr_stop": [2.0, 3.0],
        },
    ),
    StrategyFamily.VOLATILITY_REGIME: FamilySpec(
        family=StrategyFamily.VOLATILITY_REGIME,
        description="Regime filter that scales exposure by realized volatility.",
        param_grid={
            "vol_window": [20, 40],
            "target_vol": [0.10, 0.15],
        },
    ),
}


@dataclass(frozen=True)
class CandidateSpec:
    """A single (family, parameters) candidate to be evaluated."""

    family: StrategyFamily
    strategy_id: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "strategy_id": self.strategy_id,
            "parameters": dict(self.parameters),
        }


def enumerate_candidates(
    families: list[StrategyFamily] | None = None,
) -> list[CandidateSpec]:
    """Deterministically enumerate all (family, params) candidates.

    Order is stable: family enum order, then sorted parameter combinations.
    """
    selected = families or list(StrategyFamily)
    out: list[CandidateSpec] = []
    for fam in selected:
        spec = FAMILY_CATALOGUE[fam]
        for i, params in enumerate(spec.enumerate_params()):
            strategy_id = f"{fam.value}_{i:03d}"
            out.append(
                CandidateSpec(family=fam, strategy_id=strategy_id, parameters=params)
            )
    return out
