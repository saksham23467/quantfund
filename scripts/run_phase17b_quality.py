#!/usr/bin/env python3
"""Phase 17B quality report on longest discovered packages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17a.datasets import discover_zerodha_packages, load_package_bars
from quantfund.phase17a.quality import run_symbol_quality
from quantfund.phase17b.regimes import annual_coverage


def main() -> int:
    pkgs = discover_zerodha_packages()
    rows = []
    for p in pkgs:
        bars = load_package_bars(p)
        q = run_symbol_quality(bars, dataset_id=p.dataset_id)
        rows.append(
            {
                "symbol": p.symbol,
                "bars": len(bars),
                "start": p.start,
                "end": p.end,
                "hash": p.content_hash,
                "quality": {
                    "errors": q["errors"],
                    "warnings": q["warnings"],
                    "data_blocked": q["data_blocked"],
                    "missing_sessions": (q.get("calendar") or {}).get("missing_sessions"),
                    "coverage_ratio": (q.get("calendar") or {}).get("coverage_ratio"),
                },
                "annual": annual_coverage(bars),
            }
        )
    print(json.dumps({"packages": rows}, indent=2, default=str))
    return 0 if pkgs else 1


if __name__ == "__main__":
    raise SystemExit(main())
