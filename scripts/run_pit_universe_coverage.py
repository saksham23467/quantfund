#!/usr/bin/env python3
"""Build the PIT historical universe coverage report. No strategy search, no trading."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.research.universe.report import (  # noqa: E402
    build_pit_universe_report,
    write_pit_universe_report,
)


def main() -> int:
    payload = build_pit_universe_report()
    json_path = ROOT / "reports" / "pit_universe_coverage.json"
    md_path = ROOT / "reports" / "pit_universe_coverage.md"
    write_pit_universe_report(payload, json_path=json_path, md_path=md_path)

    eligible = bool(payload.get("research_eligibility"))
    print("==================================================")
    print("PIT HISTORICAL UNIVERSE COVERAGE (NO STRATEGY SEARCH)")
    print(f"membership_coverage_ratio     = {payload.get('membership_coverage_ratio')}")
    print(f"instrument_identity_coverage  = {payload.get('instrument_identity_coverage')}")
    print(f"delisted_coverage             = {payload.get('delisted_coverage')}")
    print(f"unknown_membership_count      = {payload.get('unknown_membership_count')}")
    print(f"research_eligibility          = {str(eligible).lower()}")
    print("trading_enabled               = false")
    print("--- blockers ---")
    for b in payload.get("blockers") or []:
        print(f"  [UNRESOLVED] {b}")
    print(f"report_json = {json_path}")
    print("==================================================")
    if not eligible:
        print("STOP: universe coverage is INSUFFICIENT for research (fail closed).")
    # Safety: this runner never enables trading.
    assert payload.get("trading_enabled") is False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
