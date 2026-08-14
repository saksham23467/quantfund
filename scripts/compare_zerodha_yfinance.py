#!/usr/bin/env python3
"""Diagnostic Zerodha vs yfinance comparison — does NOT change eligibility."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.providers.zerodha_historical import network_historical_allowed
from quantfund.data.zerodha_hist.compare import compare_zerodha_yfinance


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="RELIANCE")
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2024-03-31")
    p.add_argument("--force-mock", action="store_true")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments" / "zerodha_hist_demo" / "data_comparison_report.json",
    )
    args = p.parse_args()
    force_mock = args.force_mock or not network_historical_allowed()
    report = compare_zerodha_yfinance(
        symbol=args.symbol,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        out_path=args.out,
        force_mock=force_mock,
    )
    print("DIAGNOSTIC ONLY — eligibility unchanged")
    print(f"mode={'SIMULATED' if force_mock else 'REAL_ZERODHA'} vs YFINANCE")
    print(json.dumps(report, indent=2, default=str))
    print(f"wrote={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
