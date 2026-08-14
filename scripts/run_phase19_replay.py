#!/usr/bin/env python3
"""Phase 19 deterministic replay."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase19.pipeline import run_phase19_replay


def main() -> int:
    payload = run_phase19_replay(duration="1d")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("reproducible") else 1


if __name__ == "__main__":
    raise SystemExit(main())
