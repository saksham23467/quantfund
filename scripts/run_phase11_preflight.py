#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase11.certification import certify_phase11


def main() -> int:
    snap = certify_phase11(env=dict(os.environ), simulate_connectivity=True)
    print("PHASE 11 PREFLIGHT")
    print(f"research_eligibility: {snap.research_eligibility}")
    print(f"paper_eligible: {snap.paper_eligible}")
    print(f"preflight_ok: {snap.preflight_ok}")
    print(f"connectivity: {snap.connectivity.value}")
    print("live_orders: 0")
    if snap.preflight:
        for c in snap.preflight.checks:
            print(f"- {c.name}: {c.status.value} ({c.detail})")
    return 0 if snap.preflight_ok or snap.research_eligibility == "development_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
