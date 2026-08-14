#!/usr/bin/env python3
"""Deterministic Phase 2 research demo on synthetic development data.

Labeled exploratory_only / development_only — NOT final strategy validation.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from quantfund.config import PATHS
from quantfund.data.models import MarketBar
from quantfund.data.normalize import dataframe_to_bars
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)
from quantfund.data.validate import validate_bars
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.runner import ResearchRunner
from quantfund.research.splits import Period, SplitConfig
from quantfund.research.walkforward import WalkForwardConfig
from quantfund.strategies.baselines.momentum import MomentumStrategy
from quantfund.storage.registry import ExperimentRegistry


def main() -> int:
    fixture = ROOT / "tests" / "fixtures" / "synthetic_bars.csv"
    df = pd.read_csv(fixture, parse_dates=["timestamp"])
    bars = validate_bars(dataframe_to_bars(df, symbol="TEST"))

    registry = ExperimentRegistry(PATHS.experiments_dir / "registry")
    runner = ResearchRunner(registry)

    split = SplitConfig(
        train=Period(start=date(2024, 1, 2), end=date(2024, 1, 3)),
        validation=Period(start=date(2024, 1, 4), end=date(2024, 1, 5)),
        test=Period(start=date(2024, 1, 8), end=date(2024, 1, 8)),
    )
    universe = UniverseVersion(
        universe_id="nifty50",
        universe_version="demo_pit_window",
        completeness=UniverseCompleteness.FULL_PIT,
        as_of_date=date(2024, 1, 8),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 1, 8),
        source="synthetic_demo",
        members=[UniverseMember(instrument_id="NSE:TEST", symbol="TEST")],
    )

    def factory():
        return MomentumStrategy(symbol="TEST", lookback=1, threshold=-1.0)

    cfg = ExperimentConfig(
        strategy_id="momentum",
        strategy_version="1.0.0",
        parameters={
            "symbol": "TEST",
            "lookback": 1,
            "threshold": -1.0,
            "allocation": 0.95,
        },
        dataset_id="synthetic_fixture",
        dataset_version="m1_v1",
        universe_id=universe.universe_id,
        universe_version=universe.universe_version,
        feature_requests=[{"name": "momentum", "window": 1}],
        feature_versions={"momentum_1": "1.0.0"},
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        calendar_id="SYNTHETIC_SESSIONS",
        calendar_version="synthetic_fixture_v1",
        split_config=split,
        walkforward_config=WalkForwardConfig(
            train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1
        ),
        start_date="2024-01-02",
        end_date="2024-01-08",
        initial_capital=100_000,
        research_eligibility="development_only",
        sealed_evaluation=False,
        family_id="phase2_dev_demo",
        purpose="candidate",
    )

    print("=" * 60)
    print("PHASE 2 RESEARCH DEMO — development_only / exploratory_only")
    print("NOT final strategy validation. NOT evidence of profitability.")
    print("=" * 60)

    r1 = runner.evaluate(
        strategy_factory=factory,
        bars=bars,
        config=cfg,
        universe=universe,
        feature_requests=[{"name": "momentum", "window": 1}],
        run_robustness=True,
        run_walkforward=True,
    )
    cfg2 = cfg.model_copy(update={"experiment_id": "repro_" + cfg.experiment_id[:8]})
    r2 = runner.evaluate(
        strategy_factory=factory,
        bars=bars,
        config=cfg2,
        universe=universe,
        feature_requests=[{"name": "momentum", "window": 1}],
        run_robustness=True,
        run_walkforward=True,
    )

    print(f"status              : {r1.status}")
    print(f"config_hash run1    : {r1.config_hash}")
    print(f"config_hash run2    : {r2.config_hash}")
    print(f"hashes equal        : {r1.config_hash == r2.config_hash}")
    print(f"TEST sealed          : {r1.metrics_by_split.get('test')}")
    print(f"validation metrics  : {r1.metrics_by_split.get('validation')}")
    print(f"score accepted      : {(r1.score or {}).get('accepted')}")
    print(f"artifacts           : {r1.artifacts_path}")
    print(f"deflated sharpe     : {r1.deflated_sharpe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
