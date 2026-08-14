#!/usr/bin/env python3
"""Read-only environment identity check — never prints secrets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.deploy.environment import run_environment_check


def main() -> int:
    payload = run_environment_check(fetch_egress_ip=True)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    role = payload.get("execution_role")
    print()
    print(f"execution_role={role}  # LOCAL vs EC2")
    print(
        f"egress={payload.get('public_egress_ip')} "
        f"expected={payload.get('expected_zerodha_ip_if_configured')} "
        f"match={payload.get('zerodha_ip_match')}"
    )
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
