#!/usr/bin/env python3
"""Validate an external / fixture research package (Phase 5)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.providers.package_validator import validate_research_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "package_root",
        type=Path,
        help="Path to research_package/ directory",
    )
    args = parser.parse_args()
    result = validate_research_package(args.package_root)
    print(f"Package: {args.package_root}")
    print(f"Valid: {result.valid}")
    if result.content_hash:
        print(f"Content hash: {result.content_hash}")
    if result.capabilities:
        caps = result.capabilities
        print(f"Source grade: {caps.source_grade.value}")
        print(f"Exchange authority: {caps.exchange_authority}")
        print(f"License status: {caps.license_status.value}")
        print(
            "Source bar:",
            caps.can_satisfy_research_eligibility_source_bar(),
        )
    for e in result.errors:
        print(f"ERROR [{e.code}] {e.path}: {e.message}")
    for w in result.warnings:
        print(f"WARNING [{w.code}] {w.path}: {w.message}")
    return 0 if result.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
