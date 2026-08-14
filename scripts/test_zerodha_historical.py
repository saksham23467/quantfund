#!/usr/bin/env python3
"""Download/normalize Zerodha historical candles (mock by default).

REAL mode requires QUANTFUND_ALLOW_ZERODHA_HISTORICAL=1 and ZERODHA_* env vars.
Never places orders. Never prints credentials.
"""

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
from quantfund.data.zerodha_hist.package import write_zerodha_dataset_package
from quantfund.data.zerodha_hist.validation import run_quality


def main() -> int:
    p = argparse.ArgumentParser(description="Zerodha historical download (read-only)")
    p.add_argument("--symbol", default="RELIANCE")
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2024-06-28")
    p.add_argument("--interval", default="1day")
    p.add_argument("--force-mock", action="store_true")
    args = p.parse_args()
    force_mock = args.force_mock or not network_historical_allowed()
    provider = build_zerodha_historical_provider(
        env=dict(os.environ), force_mock=force_mock
    )
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    try:
        bars = provider.fetch_daily(args.symbol, start=start, end=end)
    except ZerodhaHistoricalError as exc:
        print(f"FAIL CLOSED: {exc}")
        return 1
    quality = run_quality(bars, provider=provider)
    if quality.get("data_blocked"):
        print(f"DATA_BLOCKED errors={quality['errors']}")
        print(json.dumps(quality, indent=2, default=str))
        return 2
    pkg = write_zerodha_dataset_package(
        bars=bars,
        provenance=(
            provider.last_provenance().to_dict() if provider.last_provenance() else {}
        ),
        quality_report=quality,
        instrument_metadata={"symbol": args.symbol, "interval": args.interval},
    )
    mode = "SIMULATED/MOCK" if force_mock else "REAL ZERODHA HISTORICAL API"
    print(f"mode={mode}")
    print(f"symbol={args.symbol} interval={args.interval}")
    print(f"rows={len(bars)} price_policy=unknown")
    print(f"package={pkg}")
    print(f"quality_errors={quality['errors']} warnings={quality['warnings']}")
    print("orders_submitted=0 place_order_called=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
