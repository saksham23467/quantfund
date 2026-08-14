#!/usr/bin/env python3
"""REAL Zerodha historical validation — read-only. Never prints credentials."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.zerodha_hist.envutil import merge_env_with_optional_dotenv
from quantfund.data.zerodha_hist.real_validation import (
    render_markdown_report,
    run_real_zerodha_validation,
)


def main() -> int:
    dotenv = ROOT / ".env"
    merged = merge_env_with_optional_dotenv(dotenv_path=dotenv)
    # Inject into process env for downstream yfinance/compare helpers (values never printed)
    for k, v in merged.items():
        if k.startswith("ZERODHA_") or k.startswith("QUANTFUND_"):
            os.environ.setdefault(k, v)

    out = ROOT / "experiments" / "zerodha_real_validation"
    report = run_real_zerodha_validation(out_dir=out, dotenv_path=dotenv)

    print("=============================================")
    print("QUANTFUND ZERODHA REAL HISTORICAL VALIDATION")
    print("=============================================")
    print(f"result={report.get('result')}")
    print(f"data={report.get('data')}")
    print(f"stage={report.get('stage', 'validation')}")
    if report.get("message"):
        print(report["message"])
    if report.get("error"):
        print(f"error={report.get('error')}")
    print()
    print("Security:")
    print(f"  orders_submitted={report.get('orders_submitted')}")
    print(f"  place_order_called={report.get('place_order_called')}")
    print(f"  broker_write_attempts={report.get('broker_write_attempts')}")
    print(f"  live_trading={report.get('live_trading')}")
    print(f"  kill_switch={report.get('kill_switch')}")
    print(f"  paper_trading={report.get('paper_trading')}")
    print(f"  broker_write_capability={report.get('broker_write_capability')}")
    print()
    if report.get("aggregate"):
        print("Aggregate:")
        for row in report["aggregate"]:
            print(
                f"  {row.get('symbol')}: bars={row.get('bars')} "
                f"missing={row.get('missing_sessions')} "
                f"q_err={row.get('quality_errors')} "
                f"warn={row.get('warnings')} "
                f"ca={row.get('ca_coverage')} "
                f"elig={row.get('eligibility')} "
                f"err={row.get('error')}"
            )
    print()
    print(report.get("statement") or "")
    print("=============================================")

    md = render_markdown_report(report)
    docs_path = ROOT / "docs" / "ZERODHA_REAL_DATA_VALIDATION.md"
    docs_path.write_text(md, encoding="utf-8")
    print(f"wrote_docs={docs_path}")
    print(f"wrote_json={out / 'real_validation_report.json'}")

    # Final console dump without secrets
    safe = {
        k: report[k]
        for k in (
            "ok",
            "result",
            "aggregate",
            "orders_submitted",
            "place_order_called",
            "broker_write_attempts",
            "fetch_errors",
            "yfinance_comparison",
        )
        if k in report
    }
    print(json.dumps(safe, indent=2, default=str)[:8000])
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
