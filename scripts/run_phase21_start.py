#!/usr/bin/env python3
"""Phase 21 autonomous paper session start — PAPER ONLY."""

from __future__ import annotations

import os

from quantfund.phase21.pipeline import run_phase21_session


def main() -> None:
    days = int(os.environ.get("QUANTFUND_PHASE21_DAYS", "20"))
    force_mock = os.environ.get("QUANTFUND_PHASE21_ALLOW_MOCK") == "1"
    poll = float(os.environ.get("QUANTFUND_PHASE21_POLL_SLEEP", "0"))
    report = run_phase21_session(
        duration_days=days,
        force_mock=force_mock if force_mock else None,
        poll_sleep_s=poll,
        allow_live_quote_poll=os.environ.get("QUANTFUND_PHASE21_LIVE_QUOTE") == "1",
    )
    # Never exit 0 on safety failure
    ok = report.get("assertions", {}).get("place_order_called") == 0
    ok = ok and report.get("live_orders") == 0
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main()
