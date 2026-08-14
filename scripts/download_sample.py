#!/usr/bin/env python3
"""Optional yfinance sample download for development prototyping.

Does not run as part of the default smoke test. Raw files are never modified
after download; processed Parquet is written separately.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.config import PATHS
from quantfund.data.providers.yfinance_provider import YFinanceProvider, default_india_equity
from quantfund.data.store import save_bars_parquet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument("--yahoo", default="RELIANCE.NS")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-06-30")
    args = parser.parse_args()

    instrument = default_india_equity(args.symbol, args.yahoo)
    provider = YFinanceProvider(
        [instrument],
        raw_dir=PATHS.raw_dir,
        save_raw=True,
    )
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    bars = provider.get_history(args.symbol, start=start, end=end)
    if not bars:
        print("No bars returned.")
        return 1

    out = PATHS.processed_dir / f"{args.symbol}_{args.start}_{args.end}.parquet"
    save_bars_parquet(
        bars,
        out,
        data_source=provider.name,
        data_version=f"{args.start}_{args.end}",
        metadata={"yahoo_symbol": args.yahoo, "note": "development prototype only"},
    )
    print(f"Downloaded {len(bars)} bars → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
