#!/usr/bin/env python3
"""Optional network ingest of a Stage A universe via yfinance (development only).

Produces an immutable RAW download. Building a dataset is a separate step.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.config import PATHS
from quantfund.data.models import AssetClass, Instrument
from quantfund.data.providers.yfinance_provider import YFinanceProvider
from quantfund.data.ingest.pipeline import ingest_bars_raw
from quantfund.data.universe.membership import UniverseMembershipStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-id", default="nifty50")
    parser.add_argument("--universe-version", default="stage_a_sample_v1")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-01-31")
    args = parser.parse_args()

    store = UniverseMembershipStore(PATHS.universes_dir)
    universe = store.load(args.universe_id, args.universe_version)
    print("WARNING:", universe.warnings[0] if universe.warnings else "")
    print("This ingest is development/non-exchange grade only.")

    instruments = [
        Instrument(
            symbol=m.symbol,
            name=m.name,
            exchange="NSE",
            asset_class=AssetClass.EQUITY,
            provider_symbol=m.provider_symbol or f"{m.symbol}.NS",
        )
        for m in universe.members
        if m.symbol != "TEST"  # skip synthetic member for live Yahoo fetch
    ]
    if not instruments:
        print("No non-synthetic instruments in universe.")
        return 1

    provider = YFinanceProvider(instruments, raw_dir=None, save_raw=False)
    result = ingest_bars_raw(
        provider=provider,
        instruments=instruments,
        raw_root=PATHS.raw_dir,
        start=datetime.fromisoformat(args.start),
        end=datetime.fromisoformat(args.end),
        extra_meta={
            "source_grade": "non_exchange",
            "dataset_status": "development",
            "universe_id": args.universe_id,
            "universe_version": args.universe_version,
        },
    )
    print(f"Raw download_id={result.download_id}")
    print(f"path={result.root}")
    print(f"bars={result.bar_count} checksum={result.checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
