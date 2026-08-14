#!/usr/bin/env python3
"""Phase 21 preflight — paper only; no live orders."""

from __future__ import annotations

from quantfund.phase21.pipeline import run_phase21_preflight


def main() -> None:
    payload = run_phase21_preflight()
    raise SystemExit(0 if payload.get("ok") else 1)


if __name__ == "__main__":
    main()
