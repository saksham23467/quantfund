#!/usr/bin/env python3
"""Phase 16A connectivity — MOCK by default; never places orders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase16a.health import run_broker_health_checks
from quantfund.phase16a.zerodha_readonly import build_zerodha_readonly_broker


def main() -> int:
    broker = build_zerodha_readonly_broker(force_mock=True)
    broker.connect()
    h = run_broker_health_checks(broker)
    print("PHASE 16A CONNECTIVITY (READ-ONLY / MOCK)")
    print(f"ok={h.ok}")
    for k, v in h.to_dict().items():
        if k != "errors":
            print(f"{k}={v}")
    print("order_submission=NOT IMPLEMENTED")
    print("live_orders=0")
    broker.disconnect()
    return 0 if h.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
