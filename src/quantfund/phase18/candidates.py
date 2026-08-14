"""Deterministic Phase 18 candidates and StrategySpec builders."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from quantfund.data.ingest.checksums import hash_json
from quantfund.phase18.grammar import (
    FAMILY_IDS,
    SearchMode,
    expand_family_params,
    grids_for_mode,
    search_config_payload,
)
from quantfund.strategies.spec.models import (
    FeatureRef,
    Rule,
    StrategySpec,
)


def candidate_id_for(family: str, parameters: dict[str, Any]) -> str:
    """Stable id independent of symbol / wall clock."""
    payload = {
        "family": family,
        "parameters": {k: parameters[k] for k in sorted(parameters)},
        "phase": "18",
    }
    return "p18_" + hash_json(payload)[:16]


def _feat(name: str, **params: Any) -> FeatureRef:
    return FeatureRef(feature_name=name, params=dict(params))


def build_strategy_spec(
    *,
    family: str,
    parameters: dict[str, Any],
    symbol: str,
    candidate_id: str,
) -> StrategySpec:
    """Every candidate becomes a StrategySpec (DSL where expressible)."""
    univ = "phase18_single"
    hyp = f"Phase18 fixed-grammar {family}"
    meta = {
        "phase": "18",
        "candidate_id": candidate_id,
        "strategy_family": family,
        "grammar": "fixed",
    }
    p = dict(parameters)

    if family in ("ma_cross", "trend_following"):
        fast, slow = int(p["fast"]), int(p["slow"])
        return StrategySpec(
            name=f"{family}_{fast}_{slow}",
            hypothesis=hyp,
            universe_id=univ,
            symbol=symbol,
            strategy_id=family,
            features=[_feat("sma", window=fast), _feat("sma", window=slow)],
            entry_rules=[
                Rule(op="gt", left=f"feature:sma_{fast}", right=f"feature:sma_{slow}")
            ],
            exit_rules=[
                Rule(op="lte", left=f"feature:sma_{fast}", right=f"feature:sma_{slow}")
            ],
            parameters=p,
            metadata=meta,
        )

    if family == "momentum":
        lb = int(p["lookback"])
        thr = float(p["threshold"])
        return StrategySpec(
            name=f"momentum_{lb}",
            hypothesis=hyp,
            universe_id=univ,
            symbol=symbol,
            strategy_id="momentum",
            features=[_feat("momentum", window=lb)],
            entry_rules=[Rule(op="gt", left=f"feature:momentum_{lb}", right=thr)],
            exit_rules=[Rule(op="lte", left=f"feature:momentum_{lb}", right=thr)],
            parameters=p,
            metadata=meta,
        )

    if family == "mean_reversion":
        w = int(p["window"])
        ez, xz = float(p["entry_z"]), float(p["exit_z"])
        return StrategySpec(
            name=f"mean_reversion_{w}",
            hypothesis=hyp,
            universe_id=univ,
            symbol=symbol,
            strategy_id="mean_reversion",
            features=[_feat("zscore", window=w)],
            entry_rules=[Rule(op="lt", left=f"feature:zscore_{w}", right=ez)],
            exit_rules=[Rule(op="gte", left=f"feature:zscore_{w}", right=xz)],
            parameters=p,
            metadata=meta,
        )

    if family == "vol_breakout":
        n, k = int(p["atr_n"]), float(p["k"])
        # Expressible via features; interpreter uses ATR + prior-close style via params
        return StrategySpec(
            name=f"vol_breakout_{n}_{k}",
            hypothesis=hyp,
            universe_id=univ,
            symbol=symbol,
            strategy_id="vol_breakout",
            features=[_feat("atr", window=n)],
            entry_rules=[Rule(op="gt", left=f"feature:atr_{n}", right=0.0)],
            exit_rules=[Rule(op="lte", left=f"feature:atr_{n}", right=0.0)],
            parameters=p,
            metadata={**meta, "execution_note": "factory_uses_baseline_vol_breakout"},
        )

    if family == "rsi_mean_reversion":
        return StrategySpec(
            name=f"rsi_{p['period']}",
            hypothesis=hyp,
            universe_id=univ,
            symbol=symbol,
            strategy_id="rsi_mean_reversion",
            features=[],
            entry_rules=[],
            exit_rules=[],
            parameters=p,
            metadata={**meta, "interpreter": "phase18_extra_rsi"},
        )

    if family == "donchian_breakout":
        return StrategySpec(
            name=f"donchian_{p['lookback']}",
            hypothesis=hyp,
            universe_id=univ,
            symbol=symbol,
            strategy_id="donchian_breakout",
            features=[],
            entry_rules=[],
            exit_rules=[],
            parameters=p,
            metadata={**meta, "interpreter": "phase18_extra_donchian"},
        )

    if family in ("volatility_regime_filter", "momentum_vol_filter"):
        lb = int(p["lookback"])
        vw = int(p["vol_window"])
        return StrategySpec(
            name=f"{family}_{lb}_{p['max_vol']}",
            hypothesis=hyp,
            universe_id=univ,
            symbol=symbol,
            strategy_id=family,
            features=[
                _feat("momentum", window=lb),
                _feat("rolling_vol", window=vw),
            ],
            entry_rules=[
                Rule(
                    op="and",
                    args=[
                        Rule(
                            op="gt",
                            left=f"feature:momentum_{lb}",
                            right=float(p["threshold"]),
                        ),
                        Rule(
                            op="lte",
                            left=f"feature:rolling_vol_{vw}",
                            right=float(p["max_vol"]),
                        ),
                    ],
                )
            ],
            exit_rules=[
                Rule(
                    op="or",
                    args=[
                        Rule(
                            op="lte",
                            left=f"feature:momentum_{lb}",
                            right=float(p["threshold"]),
                        ),
                        Rule(
                            op="gt",
                            left=f"feature:rolling_vol_{vw}",
                            right=float(p["max_vol"]),
                        ),
                    ],
                )
            ],
            parameters=p,
            metadata=meta,
        )

    if family == "trend_vol_filter":
        fast, slow = int(p["fast"]), int(p["slow"])
        vw = int(p["vol_window"])
        return StrategySpec(
            name=f"trend_vol_{fast}_{slow}",
            hypothesis=hyp,
            universe_id=univ,
            symbol=symbol,
            strategy_id="trend_vol_filter",
            features=[
                _feat("sma", window=fast),
                _feat("sma", window=slow),
                _feat("rolling_vol", window=vw),
            ],
            entry_rules=[
                Rule(
                    op="and",
                    args=[
                        Rule(
                            op="gt",
                            left=f"feature:sma_{fast}",
                            right=f"feature:sma_{slow}",
                        ),
                        Rule(
                            op="lte",
                            left=f"feature:rolling_vol_{vw}",
                            right=float(p["max_vol"]),
                        ),
                    ],
                )
            ],
            exit_rules=[
                Rule(
                    op="or",
                    args=[
                        Rule(
                            op="lte",
                            left=f"feature:sma_{fast}",
                            right=f"feature:sma_{slow}",
                        ),
                        Rule(
                            op="gt",
                            left=f"feature:rolling_vol_{vw}",
                            right=float(p["max_vol"]),
                        ),
                    ],
                )
            ],
            parameters=p,
            metadata=meta,
        )

    raise ValueError(f"unsupported family: {family}")


@dataclass(frozen=True)
class SearchCandidate:
    candidate_id: str
    strategy_family: str
    parameters: dict[str, Any]

    def strategy_spec(self, symbol: str) -> StrategySpec:
        return build_strategy_spec(
            family=self.strategy_family,
            parameters=self.parameters,
            symbol=symbol,
            candidate_id=self.candidate_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "strategy_family": self.strategy_family,
            "parameters": dict(self.parameters),
            "strategy_spec_template": json.loads(
                self.strategy_spec("SYMBOL").model_dump_json()
            ),
        }


def generate_candidates(mode: SearchMode = "full") -> list[SearchCandidate]:
    grids = grids_for_mode(mode)
    out: list[SearchCandidate] = []
    for family in FAMILY_IDS:
        for params in expand_family_params(family, grids):
            cid = candidate_id_for(family, params)
            out.append(
                SearchCandidate(
                    candidate_id=cid,
                    strategy_family=family,
                    parameters=params,
                )
            )
    # Deterministic order
    out.sort(key=lambda c: (c.strategy_family, c.candidate_id))
    return out


def search_config_hash(mode: SearchMode) -> str:
    return hash_json(search_config_payload(mode))
