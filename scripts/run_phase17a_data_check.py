#!/usr/bin/env python3
"""Phase 17A dataset / CA / quality check only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17a.ca import analyze_ca_for_symbol, ca_coverage_table, default_ca_file
from quantfund.phase17a.datasets import dataset_inventory, discover_zerodha_packages, load_package_bars
from quantfund.phase17a.quality import run_symbol_quality


def main() -> int:
    packages = discover_zerodha_packages()
    inv = dataset_inventory(packages)
    ca_path = default_ca_file()
    rows = []
    ca_table = []
    for pkg in packages:
        bars = load_package_bars(pkg)
        q = run_symbol_quality(bars, dataset_id=pkg.dataset_id)
        ca = analyze_ca_for_symbol(pkg.symbol, ca_file=ca_path, bars=bars)
        ca.pop("actions", None)
        ca_table.append(ca)
        rows.append(
            {
                "symbol": pkg.symbol,
                "bars": len(bars),
                "dataset_hash": pkg.content_hash,
                "quality_errors": q["errors"],
                "data_blocked": q["data_blocked"],
                "missing_sessions": (q.get("calendar") or {}).get("missing_sessions"),
            }
        )
    print(json.dumps({"inventory": inv, "symbols": rows, "ca": ca_coverage_table(ca_table)}, indent=2, default=str))
    return 0 if packages else 1


if __name__ == "__main__":
    raise SystemExit(main())
