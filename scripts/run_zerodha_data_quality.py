#!/usr/bin/env python3
"""Quality report for Zerodha historical bars (mock by default)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.providers.zerodha_historical import (
    ZerodhaHistoricalError,
    build_zerodha_historical_provider,
    network_historical_allowed,
)
from quantfund.data.zerodha_hist.validation import run_quality


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="RELIANCE")
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2024-06-28")
    p.add_argument("--force-mock", action="store_true")
    args = p.parse_args()
    force_mock = args.force_mock or not network_historical_allowed()
    provider = build_zerodha_historical_provider(env=dict(os.environ), force_mock=force_mock)
    try:
        bars = provider.fetch_daily(
            args.symbol,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
        )
    except ZerodhaHistoricalError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    q = run_quality(bars, provider=provider)
    print(
        json.dumps(
            {"ok": True, "mode": "SIMULATED" if force_mock else "REAL", **q},
            indent=2,
            default=str,
        )
    )
    return 0 if q["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
