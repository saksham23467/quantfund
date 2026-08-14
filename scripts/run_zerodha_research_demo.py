#!/usr/bin/env python3
"""Run baseline strategies on Zerodha historical data via existing research stack."""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.providers.zerodha_historical import network_historical_allowed
from quantfund.data.zerodha_hist.validation import run_zerodha_historical_validation


def main() -> int:
    force_mock = not network_historical_allowed()
    ca = ROOT / "tests" / "fixtures" / "ca" / "cf_ca_sample.csv"
    out = ROOT / "experiments" / "zerodha_research_demo"
    r = run_zerodha_historical_validation(
        symbol="RELIANCE",
        start=date(2024, 1, 1),
        end=date(2024, 6, 28),
        out_dir=out,
        force_mock=force_mock,
        env=dict(os.environ),
        ca_file=ca if ca.exists() else None,
    )
    keys = (
        "ok",
        "result",
        "data",
        "dataset_id",
        "dataset_version",
        "rows",
        "research_eligibility",
        "baselines",
        "leakage",
        "reproducibility",
        "orders_submitted",
        "place_order_called",
        "live_trading",
        "kill_switch",
    )
    print(json.dumps({k: r[k] for k in keys if k in r}, indent=2, default=str))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
