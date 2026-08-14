#!/usr/bin/env python3
"""Fetch a small NIFTY sample via yfinance and run a development-only backtest.

DEVELOPMENT_ONLY — not research / paper / live eligible.
Purpose: verify the pipeline on real public Yahoo data.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.analytics.metrics import compute_metrics
from quantfund.analytics.report import build_report_dict, render_text_report, write_reports
from quantfund.backtest.broker_sim import SlippageModel
from quantfund.backtest.costs import EquityDeliveryCostConfig, EquityDeliveryCostModel
from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.config import INITIAL_CAPITAL, PATHS
from quantfund.data.development.config import DATA_CLASS_DEVELOPMENT
from quantfund.data.development.ingest import ingest_development_data
from quantfund.data.development.config import DevelopmentIngestConfig
from quantfund.data.development.normalize import load_bars_directory
from quantfund.data.validate import validate_bars
from quantfund.risk.limits import RiskConfig
from quantfund.strategies.baselines.momentum import MomentumStrategy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="RELIANCE", help="NSE symbol to backtest")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Reuse newest development dataset under data/development/",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("YFINANCE DEVELOPMENT BACKTEST")
    print("Data class: DEVELOPMENT_DATA")
    print("Research eligibility: DEVELOPMENT_ONLY")
    print("NOT final strategy validation.")
    print("=" * 60)

    if args.skip_ingest:
        root = PATHS.development_dir / "india_eq" / "india_eq_development"
        versions = sorted(root.glob("*")) if root.exists() else []
        if not versions:
            print("No development dataset found; run without --skip-ingest")
            return 1
        dataset_root = versions[-1]
        print(f"Reusing dataset: {dataset_root}")
        bars = load_bars_directory(dataset_root)
    else:
        cfg = DevelopmentIngestConfig(
            allow_network_fetch=True,
            symbols=["RELIANCE.NS", "TCS.NS", "INFY.NS"],
            dataset_version=(
                f"yf_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
            ),
        )
        # Pass date window via provider by temporarily setting on config extras
        from quantfund.data.development.provider import DevelopmentDataProvider

        provider = DevelopmentDataProvider.from_yfinance_fetch(
            cfg.symbols,
            start=datetime.fromisoformat(args.start),
            end=datetime.fromisoformat(args.end),
        )
        # Store via normal ingest path using in-memory → write by using file path
        # after materializing to a temp bars dir under development/
        tmp = PATHS.development_dir / "_yf_staging" / cfg.dataset_version
        if tmp.exists():
            import shutil

            shutil.rmtree(tmp)
        (tmp / "bars").mkdir(parents=True)
        by_sym: dict[str, list] = {}
        for b in provider._bars:
            by_sym.setdefault(b.symbol, []).append(b)
        import pandas as pd
        from quantfund.data.normalize import bars_to_dataframe

        for sym, sym_bars in by_sym.items():
            bars_to_dataframe(sorted(sym_bars, key=lambda x: x.timestamp)).to_csv(
                tmp / "bars" / f"{sym}.csv", index=False
            )

        result = ingest_development_data(
            DevelopmentIngestConfig(
                file_path=tmp,
                dataset_version=cfg.dataset_version,
                allow_network_fetch=False,
            )
        )
        print()
        print(f"Ingest: {'SUCCESS' if result.success else 'FAIL'}")
        print(f"Dataset root: {result.root}")
        print(f"Research eligible: {result.research_eligible}")
        print(f"Paper eligible: {result.paper_eligible}")
        print(f"Live eligible: {result.live_eligible}")
        bars = load_bars_directory(result.root) if result.root else []

    symbol = args.symbol.replace(".NS", "")
    bars = validate_bars([b for b in bars if b.symbol == symbol])
    if len(bars) < args.lookback + 5:
        print(f"Not enough bars for {symbol}: {len(bars)}")
        return 1

    print(f"\nBars for {symbol}: {len(bars)}")
    print(f"Range: {bars[0].timestamp.date()} → {bars[-1].timestamp.date()}")

    strategy = MomentumStrategy(
        symbol=symbol, lookback=args.lookback, threshold=0.0, allocation=0.95
    )
    config = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        data_source="yfinance",
        data_version="development",
        dataset_id="india_eq_development",
        dataset_version="yfinance_sample",
        research_eligibility="development_only",
        data_class=DATA_CLASS_DEVELOPMENT,
        source_grade="non_exchange",
        start_date=bars[0].timestamp,
        end_date=bars[-1].timestamp,
        risk=RiskConfig(
            max_order_value=INITIAL_CAPITAL,
            max_position_value=INITIAL_CAPITAL,
            max_total_exposure=INITIAL_CAPITAL,
        ),
        dataset_warnings=[
            "yfinance/non_exchange DEVELOPMENT_ONLY — not final validation"
        ],
    )
    engine = BacktestEngine(
        strategy,
        config=config,
        cost_model=EquityDeliveryCostModel(EquityDeliveryCostConfig()),
        slippage_model=SlippageModel(bps=5.0),
    )
    result = engine.run(bars)
    report = build_report_dict(result, compute_metrics(result))
    out = PATHS.experiments_dir / "yfinance_dev_backtest" / result.experiment_id
    json_path, text_path = write_reports(result, out)

    print()
    print(render_text_report(report))
    print()
    print(f"data_class={DATA_CLASS_DEVELOPMENT}")
    print("research_eligibility=development_only")
    print("Research eligible: FALSE")
    print("Paper eligible: FALSE")
    print("Live eligible: FALSE")
    print(f"Reports: {out}")
    print(f"  JSON: {json_path}")
    print(f"  Text: {text_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
