#!/usr/bin/env python3
"""Phase 15 read-only connectivity — never submits orders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase15.connectivity import probe_readonly_connectivity


def main() -> int:
    r = probe_readonly_connectivity()
    print("PHASE 15 CONNECTIVITY (READ-ONLY)")
    print(f"configured={r['configured']}")
    print(f"skipped={r['skipped']}")
    print(f"mode={r['mode']}")
    print(f"can_place_orders={r['can_place_orders']}")
    print(f"place_order_called={r['place_order_called']}")
    print(f"live_trading={r['live_trading']}")
    print(f"broker_submissions={r['broker_submissions']}")
    if r["skipped"]:
        print("No credentials — skipped real probe; simulated refusal proven.")
    return 0 if r["place_order_called"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
