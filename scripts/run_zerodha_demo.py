#!/usr/bin/env python3
"""Zerodha historical validation demo — MOCK by default; real only if opted in.

Never places broker orders. Never prints credentials.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.providers.zerodha_historical import network_historical_allowed
from quantfund.data.zerodha_hist.validation import run_zerodha_historical_validation


def main() -> int:
    allow_real = network_historical_allowed()
    force_mock = not allow_real
    ca = ROOT / "tests" / "fixtures" / "ca" / "cf_ca_sample.csv"
    out = ROOT / "experiments" / "zerodha_hist_demo"
    r = run_zerodha_historical_validation(
        symbol="RELIANCE",
        start=date(2024, 1, 1),
        end=date(2024, 6, 28),
        out_dir=out,
        force_mock=force_mock,
        env=dict(os.environ),
        ca_file=ca if ca.exists() else None,
    )
    print("=============================================")
    print("QUANTFUND ZERODHA HISTORICAL VALIDATION")
    print("=============================================")
    print()
    print(f"Provider: {r['provider']}")
    print(f"Data: {r['data']}")
    print(f"Exchange: {r['exchange']}")
    print(f"Interval: {r['interval']}")
    print()
    print("Dataset:")
    print(f"  ID: {r.get('dataset_id')}")
    print(f"  Version: {r.get('dataset_version')}")
    print(f"  Rows: {r['rows']}")
    print(f"  Symbols: {r.get('symbols')}")
    print(f"  Start: {r['start']}")
    print(f"  End: {r['end']}")
    print()
    print("Quality:")
    print(f"  Errors: {r['quality']['errors']}")
    print(f"  Warnings: {r['quality']['warnings']}")
    print()
    print("Corporate actions:")
    print(f"  Coverage: {r['corporate_actions']}")
    print()
    print("Eligibility:")
    print(f"  Research: {r['research_eligibility']}")
    print(f"  Reason: {r['eligibility'].get('reason', [])[:3]}")
    print()
    print("Strategies tested:")
    for name in (
        "buy_and_hold",
        "ma_cross",
        "momentum",
        "mean_reversion",
        "vol_breakout",
    ):
        st = (r.get("baselines") or {}).get("strategies", {}).get(name, {})
        print(f"  {name}: {st.get('status', r.get('baselines', {}).get('status', 'N/A'))}")
    print()
    print("Backtest:")
    print(f"  Orders: {(r.get('next_bar_open') or {}).get('orders', 'n/a')}")
    print(f"  Fills: {(r.get('next_bar_open') or {}).get('fills', 'n/a')}")
    print(f"  Execution: {r['next_bar_open'].get('execution', 'NEXT_BAR_OPEN')}")
    print(f"  Leakage: {r['leakage'].get('status')}")
    print(f"  Reproducibility: {r['reproducibility'].get('status')}")
    print()
    print("Broker:")
    print(f"  Read: {r['broker_read']}")
    print(f"  Write: {r['broker_write']}")
    print(f"  Orders submitted: {r['orders_submitted']}")
    print(f"  place_order_called: {r['place_order_called']}")
    print(f"  Live trading: {r['live_trading']}")
    print(f"  Kill switch: {r['kill_switch']}")
    print()
    print("=============================================")
    print(f"RESULT: {r['result']}")
    print("=============================================")
    if force_mock:
        print()
        print(
            "NOTE: Ran with SIMULATED/MOCK transport. "
            "Set QUANTFUND_ALLOW_ZERODHA_HISTORICAL=1 and ZERODHA_* env vars "
            "for REAL historical API (still read-only; no orders)."
        )
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
