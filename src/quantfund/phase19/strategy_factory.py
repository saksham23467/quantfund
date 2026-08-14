"""Build immutable strategy factories from Phase 18 candidates."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from quantfund.phase18.candidates import SearchCandidate, build_strategy_spec
from quantfund.phase18.factories import strategy_factory_for
from quantfund.phase19.selection import PaperCandidate
from quantfund.strategies.base import Strategy
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy
from quantfund.strategies.spec.models import StrategySpec


def strategy_and_spec_for(
    candidate: PaperCandidate, *, symbol: str
) -> tuple[Callable[[], Strategy], StrategySpec]:
    if candidate.strategy_family == "buy_and_hold" or candidate.source.endswith(
        "fallback_sandbox"
    ):
        alloc = float(candidate.parameters.get("allocation", 0.5))

        def factory() -> Strategy:
            return BuyAndHoldStrategy(symbol=symbol, allocation=alloc)

        spec = StrategySpec(
            name="buy_and_hold_sandbox",
            hypothesis="Phase19 sandbox fallback",
            universe_id="phase19_single",
            symbol=symbol,
            strategy_id="buy_and_hold",
            parameters={"allocation": alloc, "symbol": symbol},
            metadata={
                "phase": "19",
                "candidate_id": candidate.candidate_id,
                "sandbox": True,
            },
        )
        return factory, spec

    sc = SearchCandidate(
        candidate_id=candidate.candidate_id,
        strategy_family=candidate.strategy_family,
        parameters=dict(candidate.parameters),
    )
    spec = build_strategy_spec(
        family=candidate.strategy_family,
        parameters=dict(candidate.parameters),
        symbol=symbol,
        candidate_id=candidate.candidate_id,
    )
    return strategy_factory_for(sc, symbol=symbol), spec


def feature_requests_for_candidate(candidate: PaperCandidate) -> list[dict[str, Any]]:
    from quantfund.phase18.factories import feature_requests_for
    from quantfund.phase18.candidates import SearchCandidate

    if candidate.strategy_family == "buy_and_hold":
        return []
    sc = SearchCandidate(
        candidate_id=candidate.candidate_id,
        strategy_family=candidate.strategy_family,
        parameters=dict(candidate.parameters),
    )
    return feature_requests_for(sc)
