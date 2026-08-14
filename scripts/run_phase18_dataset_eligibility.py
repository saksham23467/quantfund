#!/usr/bin/env python3
"""Phase 18 research-dataset eligibility gate — dataset only, no strategy search."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase18.dataset_eligibility import run_phase18_dataset_eligibility


def main() -> int:
    payload = run_phase18_dataset_eligibility(write_reports=True)
    print("==================================================")
    print("PHASE 18 RESEARCH DATASET ELIGIBILITY (NO STRATEGY SEARCH)")
    print(f"research_eligible = {str(payload.get('research_eligible')).lower()}")
    print(f"paper_candidate = {str(payload.get('paper_candidate')).lower()}")
    print("live_enabled = false")
    print("orders_submitted = 0")
    print("place_order_called = 0")
    print(f"stopped_at_blocker = {payload.get('stopped_at_blocker')}")
    print("--- blocker ledger ---")
    for b in payload.get("blocker_ledger") or []:
        print(f"  [{b['status']:10s}] {b['id']}")
    print("==================================================")
    s = payload.get("safety") or {}
    assert s.get("place_order_called") == 0
    assert s.get("orders_submitted") == 0
    assert s.get("live_trading") == "DISABLED"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
