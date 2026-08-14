#!/usr/bin/env python3
"""Phase 4 AI Strategy Factory demo — MockStrategyGenerator only.

DEVELOPMENT_ONLY. No edge claims. No LLM. No brokers. No TEST access.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.ai.genealogy import canonical_strategy_hash
from quantfund.ai.models import GenerationRequest
from quantfund.ai.pipeline import PipelineContext, StrategyResearchPipeline
from quantfund.config import PATHS
from quantfund.data.models import MarketBar
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.splits import Period, SplitConfig
from quantfund.storage.registry import ExperimentRegistry


def _bars() -> list[MarketBar]:
    closes = [100 + i * 0.5 for i in range(20)]
    out = []
    day = 2
    for i, c in enumerate(closes):
        # skip weekends roughly by using sequential weekdays in January
        d = 2 + i
        if d > 31:
            break
        out.append(
            MarketBar(
                timestamp=datetime(2024, 1, d),
                symbol="TEST",
                open=c,
                high=c + 1,
                low=c - 1,
                close=c,
                volume=1000,
            )
        )
    return out


def main() -> int:
    bars = _bars()
    registry = ExperimentRegistry(PATHS.experiments_dir / "registry_phase4")
    pipe = StrategyResearchPipeline(registry)

    universe = UniverseVersion(
        universe_id="nifty50",
        universe_version="phase4_demo_pit",
        completeness=UniverseCompleteness.FULL_PIT,
        as_of_date=date(2024, 1, 21),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 1, 21),
        source="phase4_demo",
        members=[UniverseMember(instrument_id="NSE:TEST", symbol="TEST")],
    )

    cfg = ExperimentConfig(
        strategy_id="placeholder",
        strategy_version="1.0.0",
        parameters={},
        dataset_id="india_eq_pilot_phase35",
        dataset_version="v1_synthetic",
        universe_id=universe.universe_id,
        universe_version=universe.universe_version,
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        split_config=SplitConfig(
            train=Period(start=date(2024, 1, 2), end=date(2024, 1, 8)),
            validation=Period(start=date(2024, 1, 9), end=date(2024, 1, 14)),
            test=Period(start=date(2024, 1, 15), end=date(2024, 1, 20)),
        ),
        start_date="2024-01-02",
        end_date="2024-01-20",
        initial_capital=100_000,
        research_eligibility="development_only",
        sealed_evaluation=False,
        family_id="phase4_demo",
    )

    req = GenerationRequest(
        universe_id="nifty50",
        symbol="TEST",
        number_of_candidates=20,
        random_seed=42,
        include_malformed_fixtures=True,
        family_id="phase4_demo",
        research_objective="infrastructure_verification_only",
    )

    batch = pipe.run(
        req,
        PipelineContext(
            bars=bars,
            base_config=cfg,
            universe=universe,
            certified_eligibility="development_only",
            run_robustness=False,
        ),
    )

    print("PHASE 4 — AI STRATEGY FACTORY")
    print("=============================")
    print()
    print(f"Generated:   {batch.generated_count}")
    print(f"Valid:       {batch.valid_count}")
    print(f"Invalid:     {batch.invalid_count}")
    print(f"Duplicates:  {batch.duplicate_count}")
    print(f"Evaluated:   {batch.evaluated_count}")
    print(f"Rejected:    {batch.rejected_count}")
    print(f"Accepted:    {batch.accepted_count}")
    print()
    print("Dataset:")
    print("  india_eq_pilot_phase35 / v1_synthetic")
    print()
    print("Eligibility:")
    print(f"  {batch.research_eligibility.upper()}")
    for b in batch.eligibility_blockers:
        print(f"  blocker: {b}")
    print()
    print("AI access to TEST:")
    print("  DENIED")
    print()
    print("Arbitrary code execution:")
    print("  DENIED")
    print()
    print("Live trading:")
    print("  DISABLED")
    print()
    print("Brokers:")
    print("  NONE")
    print()
    print("Trial count (all families in batch):")
    print(f"  n_experiments={batch.n_experiments}")
    for fid, n in sorted(batch.family_trial_counts.items()):
        print(f"  {fid}: {n}")
    print()
    if batch.specs:
        ex = batch.specs[0]
        print("Example StrategySpec:")
        print(f"  name: {ex.name}")
        print(f"  strategy_id: {ex.effective_strategy_id()}")
        print(f"  family_id: {ex.metadata.get('family_id')}")
        print(f"  generation: {ex.metadata.get('generation_number')}")
        print(f"  mutation_type: {ex.metadata.get('mutation_type')}")
        print(f"  canonical_hash: {ex.metadata.get('canonical_hash') or canonical_strategy_hash(ex)}")
        print(f"  hypothesis: {ex.hypothesis}")
    print()
    print("NOTE: No strategy has discovered an edge.")
    print("DEVELOPMENT_ONLY infrastructure demonstration only.")
    assert batch.accepted_count == 0
    assert batch.generated_count == 20
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
