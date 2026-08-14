#!/usr/bin/env python3
"""Phase 19 preflight — paper isolation proofs; no live orders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase19.pipeline import run_phase19_preflight


def main() -> int:
    payload = run_phase19_preflight()
    print(f"ok={payload.get('ok')} mode={payload.get('mode')}")
    print(f"live_trading={payload.get('live_trading')}")
    print(f"safety_ok={(payload.get('safety') or {}).get('ok')}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
