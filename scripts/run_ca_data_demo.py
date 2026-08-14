#!/usr/bin/env python3
"""Historical local CA ingest demo — DEVELOPMENT_ONLY / non_exchange.

Usage:
  make ca-data-demo
  QUANTFUND_HISTORICAL_CA_FILE=/path/to/CF-CA-....csv make ca-data-demo
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.corporate_actions.historical_local import ingest_historical_ca

DEFAULT_CANDIDATES = [
    Path(os.environ["QUANTFUND_HISTORICAL_CA_FILE"])
    if os.environ.get("QUANTFUND_HISTORICAL_CA_FILE")
    else None,
    Path.home() / "Downloads" / "CF-CA-equities-01-01-2009-to-01-08-2026.csv",
    ROOT / "tests" / "fixtures" / "ca" / "cf_ca_sample.csv",
]


def main() -> int:
    source = None
    for cand in DEFAULT_CANDIDATES:
        if cand is not None and cand.is_file():
            source = cand
            break
    if source is None:
        print("ERROR: historical CA source file not found.")
        print("Set QUANTFUND_HISTORICAL_CA_FILE=/absolute/path/to/CF-CA-....csv")
        print("Expected default:", DEFAULT_CANDIDATES[1])
        return 2

    print(f"Ingesting: {source}")
    result = ingest_historical_ca(source)
    print()
    print(result.report_text)
    print()
    print(f"Raw root: {result.raw_root}")
    print(f"Normalized root: {result.normalized_root}")
    print(f"Source hash: {result.source_hash}")
    print(f"Unresolved identity: {result.metrics.unresolved_identity_rows}")
    print(f"Research eligible: {result.research_eligible}")
    print("Phase 8 started: FALSE")
    print("Brokers added: FALSE")
    return 0 if result.success and not result.research_eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
