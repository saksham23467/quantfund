#!/usr/bin/env python3
"""Phase 12 deterministic replay A==B."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase12.demo import run_phase12_replay_pair


def main() -> int:
    r = run_phase12_replay_pair()
    print("PHASE 12 REPLAY")
    print(f"identical: {r['identical']}")
    print(f"hash_a: {r['hash_a']}")
    print(f"hash_b: {r['hash_b']}")
    print(f"paper_orders: {r['paper_orders']}")
    print(f"paper_fills: {r['paper_fills']}")
    print(f"live_orders: {r['live_orders']}")
    return 0 if r["identical"] and r["paper_fills"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
