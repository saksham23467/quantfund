#!/usr/bin/env python3
"""Download multi-year REAL Zerodha historical packages (read-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17b.download import download_phase17b_universe


def main() -> int:
    report = download_phase17b_universe(force_mock=False)
    # Never print secrets — summary only
    summary = {
        "ok": report.get("ok"),
        "status": report.get("status"),
        "data": report.get("data"),
        "requested_start": report.get("requested_start"),
        "requested_end": report.get("requested_end"),
        "bundle_path": report.get("bundle_path"),
        "members": [
            {
                "symbol": m.get("symbol"),
                "status": m.get("status"),
                "bars": m.get("bars"),
                "actual_start": m.get("actual_start"),
                "actual_end": m.get("actual_end"),
                "dataset_id": m.get("dataset_id"),
                "content_hash": m.get("content_hash"),
                "error": m.get("error"),
            }
            for m in (report.get("members") or [])
        ],
        "orders_submitted": report.get("orders_submitted"),
        "place_order_called": report.get("place_order_called"),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
