#!/usr/bin/env python3
"""Phase 6 campaign orchestration demo — DEVELOPMENT_ONLY infrastructure only.

Expected:
  Campaign: SUCCESS / FINALIZED
  Dataset eligibility: DEVELOPMENT_ONLY
  Accepted: 0
  Claims: NONE

No LLM. No brokers. No genetic search. No research claims.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.config import PATHS
from quantfund.data.models import MarketBar
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)
from quantfund.research.campaign import CampaignPurpose, ResearchCampaignConfig
from quantfund.research.campaign_runner import CampaignRunner
from quantfund.research.splits import Period, SplitConfig
from quantfund.storage.registry import ExperimentRegistry


def _weekday_bars(symbol: str = "TEST", n: int = 60) -> list[MarketBar]:
    """Synthetic weekday bars for campaign infrastructure demo."""
    out: list[MarketBar] = []
    day = date(2024, 1, 2)
    i = 0
    price = 100.0
    while len(out) < n:
        if day.weekday() < 5:
            price = price + (0.3 if i % 7 else -0.2) + (i % 5) * 0.05
            out.append(
                MarketBar(
                    timestamp=datetime(day.year, day.month, day.day),
                    symbol=symbol,
                    open=price,
                    high=price + 1,
                    low=price - 1,
                    close=price,
                    volume=1000 + i,
                )
            )
            i += 1
        day += timedelta(days=1)
    return out


def main() -> int:
    bars = _weekday_bars()
    dates = [b.timestamp.date() for b in bars]
    train_end = dates[24]
    val_start = dates[25]
    val_end = dates[39]
    test_start = dates[40]
    test_end = dates[-1]

    registry = ExperimentRegistry(PATHS.experiments_dir / "registry_phase6")
    runner = CampaignRunner(
        registry, artifacts_root=PATHS.experiments_dir / "campaigns_phase6"
    )

    universe = UniverseVersion(
        universe_id="nifty50",
        universe_version="phase6_demo_pit",
        completeness=UniverseCompleteness.FULL_PIT,
        as_of_date=test_end,
        effective_start=dates[0],
        effective_end=test_end,
        source="phase6_demo_synthetic",
        members=[UniverseMember(instrument_id="NSE:TEST", symbol="TEST")],
    )

    config = ResearchCampaignConfig(
        purpose=CampaignPurpose.EXPLORATORY_DEVELOPMENT,
        dataset_id="india_eq_pilot_phase35",
        dataset_version="v1_synthetic",
        universe_id=universe.universe_id,
        universe_version=universe.universe_version,
        candidate_budget=20,
        experiment_budget=40,
        candidate_generator="mock",
        walkforward_enabled=False,
        split_config=SplitConfig(
            train=Period(start=dates[0], end=train_end),
            validation=Period(start=val_start, end=val_end),
            test=Period(start=test_start, end=test_end),
        ),
        certified_eligibility="development_only",
        source_grade="synthetic",
        family_id="phase6_demo",
        random_seed=42,
        symbol="TEST",
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        feature_requests=[
            {"name": "momentum", "params": {"window": 5}},
            {"name": "sma", "params": {"window": 3}},
            {"name": "sma", "params": {"window": 8}},
            {"name": "rolling_vol", "params": {"window": 5}},
            {"name": "zscore", "params": {"window": 5}},
        ],
    )

    print("PHASE 6 — RESEARCH CAMPAIGN ORCHESTRATION")
    print("=========================================")
    print()
    print(f"config_hash: {config.compute_hash()}")
    print(f"candidate_budget: {config.candidate_budget}")
    print(f"experiment_budget: {config.experiment_budget}")
    print()

    result = runner.run(config, bars=bars, universe=universe)

    print(f"Campaign: SUCCESS")
    print(f"Final state: {result.final_state}")
    print(f"Dataset eligibility: {config.certified_eligibility.upper()}")
    print(f"Accepted: {result.accepted_count}")
    print(f"Claims: {result.claims}")
    print()
    print("Infrastructure validation only — not evidence of edge.")
    print("No LLM. No brokers. No paper/live trading. No genetic search.")
    if result.report_path:
        print(f"Report: {result.report_path / 'campaign_report.txt'}")
    print()
    text = (result.report_path / "campaign_report.txt").read_text(encoding="utf-8")
    print(text)

    if result.accepted_count != 0 or result.claims != "NONE":
        print("BUG: development_only campaign must have accepted=0 and claims=NONE")
        return 2
    if result.final_state != "FINALIZED":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
