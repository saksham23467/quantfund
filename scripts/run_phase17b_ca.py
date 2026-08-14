#!/usr/bin/env python3
"""Phase 17B CA coverage table for discovered packages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17a.ca import analyze_ca_for_symbol, ca_coverage_table, default_ca_file
from quantfund.phase17a.datasets import discover_zerodha_packages, load_package_bars


def main() -> int:
    ca = default_ca_file()
    rows = []
    for p in discover_zerodha_packages():
        bars = load_package_bars(p)
        info = analyze_ca_for_symbol(p.symbol, ca_file=ca, bars=bars)
        info.pop("actions", None)
        rows.append(info)
    print(json.dumps({"ca_file": str(ca) if ca else None, "table": ca_coverage_table(rows), "detail": rows}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
