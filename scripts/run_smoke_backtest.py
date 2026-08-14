#!/usr/bin/env python3
"""Smoke backtest: buy-and-hold on synthetic (or optional yfinance) data.

Purpose: verify infrastructure. Not a profitability claim.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.analytics.metrics import compute_metrics
from quantfund.analytics.report import render_text_report, build_report_dict, write_reports
from quantfund.backtest.broker_sim import SlippageModel
from quantfund.backtest.costs import EquityDeliveryCostConfig, EquityDeliveryCostModel
from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.config import INITIAL_CAPITAL, PATHS
from quantfund.data.models import MarketBar
from quantfund.data.normalize import dataframe_to_bars
from quantfund.data.store import save_bars_parquet
from quantfund.data.validate import validate_bars
from quantfund.risk.limits import RiskConfig
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy
import pandas as pd


def load_synthetic_bars(path: Path) -> list[MarketBar]:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    symbol = str(df["symbol"].iloc[0])
    bars = dataframe_to_bars(df, symbol=symbol)
    return validate_bars(bars)


def main() -> int:
    parser = argparse.ArgumentParser(description="QuantFund Milestone 1 smoke backtest")
    parser.add_argument(
        "--data",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "synthetic_bars.csv",
        help="CSV path (default: synthetic fixture)",
    )
    parser.add_argument("--symbol", default=None, help="Override symbol")
    parser.add_argument(
        "--capital",
        type=float,
        default=INITIAL_CAPITAL,
        help="Initial capital INR",
    )
    args = parser.parse_args()

    bars = load_synthetic_bars(args.data)
    symbol = args.symbol or bars[0].symbol

    # Persist processed copy for reproducibility demo
    PATHS.processed_dir.mkdir(parents=True, exist_ok=True)
    processed = PATHS.processed_dir / f"{symbol}_synthetic_m1.parquet"
    save_bars_parquet(
        bars,
        processed,
        data_source="synthetic_fixture",
        data_version="m1_v1",
        metadata={"label": "SYNTHETIC", "path": str(args.data)},
    )

    strategy = BuyAndHoldStrategy(symbol=symbol, allocation=0.95)
    config = BacktestConfig(
        initial_capital=args.capital,
        data_source="synthetic_fixture",
        data_version="m1_v1",
        start_date=bars[0].timestamp,
        end_date=bars[-1].timestamp,
        risk=RiskConfig(
            max_order_value=args.capital,
            max_position_value=args.capital,
            max_total_exposure=args.capital,
        ),
    )
    engine = BacktestEngine(
        strategy,
        config=config,
        cost_model=EquityDeliveryCostModel(EquityDeliveryCostConfig()),
        slippage_model=SlippageModel(bps=5.0),
    )
    result = engine.run(bars)
    metrics = compute_metrics(result)
    report = build_report_dict(result, metrics)

    out_dir = PATHS.experiments_dir / result.experiment_id
    json_path, text_path = write_reports(result, out_dir)

    print(render_text_report(report))
    print()
    print(f"Reports written to: {out_dir}")
    print(f"  JSON: {json_path}")
    print(f"  Text: {text_path}")
    print(f"Processed parquet: {processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
