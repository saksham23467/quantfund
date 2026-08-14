#!/usr/bin/env python3
"""EC2 preflight — fail closed; never prints secrets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.deploy.ec2_preflight import run_ec2_preflight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-non-ec2",
        action="store_true",
        help="Run checks on LOCAL/Mac (for tooling validation only).",
    )
    args = parser.parse_args()
    payload = run_ec2_preflight(require_ec2=not args.allow_non_ec2)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    print()
    print(f"result={payload.get('result')} role={payload.get('execution_role')}")
    if payload.get("problems"):
        print("problems:", payload["problems"])
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
