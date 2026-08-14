#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase11.replay_cert import run_deterministic_replay_pair


def main() -> int:
    r = run_deterministic_replay_pair()
    print("PHASE 11 REPLAY")
    print(f"identical: {r.identical}")
    print(f"hash_a: {r.hash_a}")
    print(f"hash_b: {r.hash_b}")
    print(f"live_orders: {r.details['a']['live_orders']}")
    return 0 if r.identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
