#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase14.health import HealthStatus, aggregate_health


def main() -> int:
    h = aggregate_health(
        data_ok=True,
        data_stale=False,
        engine_ok=True,
        risk_ok=True,
        journal_ok=True,
        reconciliation_ok=True,
        kill_switch_armed=True,
        kill_switch_triggered=False,
        session_orders_allowed=True,
    )
    print("PHASE 14 HEALTH")
    print(h.to_dict())
    return 0 if h.overall == HealthStatus.HEALTHY else 1


if __name__ == "__main__":
    raise SystemExit(main())
