"""Phase 2 research pipeline on synthetic bars (development_only)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from quantfund.data.models import MarketBar
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.runner import ResearchRunner
from quantfund.research.splits import ChronologicalSplit, Period, SealedTestSetError, SplitConfig
from quantfund.research.walkforward import WalkForwardConfig
from quantfund.strategies.baselines.momentum import MomentumStrategy
from quantfund.storage.registry import ExperimentRegistry
import pytest


def _bars() -> list[MarketBar]:
    # Monotone upward so momentum > 0
    closes = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]
    days = list(range(2, 12))
    return [
        MarketBar(
            timestamp=datetime(2024, 1, d),
            symbol="TEST",
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1000,
        )
        for d, c in zip(days, closes, strict=True)
    ]


def test_research_runner_exploratory_and_reproducible(tmp_path: Path):
    bars = _bars()
    registry = ExperimentRegistry(tmp_path / "registry")
    runner = ResearchRunner(registry)
    split = SplitConfig(
        train=Period(start=date(2024, 1, 2), end=date(2024, 1, 4)),
        validation=Period(start=date(2024, 1, 5), end=date(2024, 1, 7)),
        test=Period(start=date(2024, 1, 8), end=date(2024, 1, 11)),
    )
    # Use FULL_PIT interval so membership is tradeable in the synthetic window.
    # Dataset eligibility remains development_only (exploratory).
    universe = UniverseVersion(
        universe_id="nifty50",
        universe_version="test_full_pit_window",
        completeness=UniverseCompleteness.FULL_PIT,
        as_of_date=date(2024, 1, 11),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 1, 11),
        source="test",
        members=[UniverseMember(instrument_id="NSE:TEST", symbol="TEST")],
    )

    def factory():
        return MomentumStrategy(symbol="TEST", lookback=2, threshold=0.0)

    cfg1 = ExperimentConfig(
        strategy_id="momentum",
        strategy_version="1.0.0",
        parameters={"symbol": "TEST", "lookback": 2, "threshold": 0.0, "allocation": 0.95},
        dataset_id="synthetic_dev",
        dataset_version="m1_v1",
        universe_id="nifty50",
        universe_version="stage_a_sample_v1",
        feature_requests=[{"name": "momentum", "window": 2}],
        feature_versions={"momentum_2": "1.0.0"},
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        calendar_id="FAKE_TEST",
        calendar_version="fake_v1",
        split_config=split,
        walkforward_config=WalkForwardConfig(
            train_sessions=3, validation_sessions=1, test_sessions=1, step_sessions=2
        ),
        start_date="2024-01-02",
        end_date="2024-01-11",
        initial_capital=100_000,
        research_eligibility="development_only",
        sealed_evaluation=False,
        family_id="phase2_demo",
        purpose="candidate",
    )
    r1 = runner.evaluate(
        strategy_factory=factory,
        bars=bars,
        config=cfg1,
        universe=universe,
        feature_requests=[{"name": "momentum", "window": 2}],
        run_robustness=True,
        run_walkforward=True,
    )
    assert r1.status == "exploratory_only"
    assert r1.metrics_by_split["test"]["sealed"] is True
    assert "development_only" in "".join(r1.warnings).lower() or r1.status == "exploratory_only"
    assert (Path(r1.artifacts_path) / "research_report.json").exists()

    cfg2 = cfg1.model_copy(update={"experiment_id": "second_run_id"})
    r2 = runner.evaluate(
        strategy_factory=factory,
        bars=bars,
        config=cfg2,
        universe=universe,
        feature_requests=[{"name": "momentum", "window": 2}],
        run_robustness=True,
        run_walkforward=True,
    )
    assert r1.config_hash == r2.config_hash
    assert r1.metrics_by_split["validation"].get("number_of_trades") == r2.metrics_by_split[
        "validation"
    ].get("number_of_trades")


def test_test_not_accessible_without_seal():
    bars = _bars()
    split = ChronologicalSplit.from_bars(
        bars,
        SplitConfig(
            train=Period(start=date(2024, 1, 2), end=date(2024, 1, 4)),
            validation=Period(start=date(2024, 1, 5), end=date(2024, 1, 7)),
            test=Period(start=date(2024, 1, 8), end=date(2024, 1, 11)),
        ),
    )
    with pytest.raises(SealedTestSetError):
        split.get_test_bars()
