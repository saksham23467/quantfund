#!/usr/bin/env python3
"""Phase 17C full demo: certify multi-year Zerodha packages + baseline regression."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17c.pipeline import run_phase17c_certification, write_phase17c_docs


def main() -> int:
    payload = run_phase17c_certification(
        run_baseline_regression=True,
        write_certified_packages=True,
    )
    write_phase17c_docs(payload, ROOT / "docs" / "PHASE17C_DATASET_CERTIFICATION.md")

    print("==================================================")
    print("QUANTFUND PHASE 17C")
    print("RESEARCH DATASET CERTIFICATION & DATA QUALITY")
    print("==================================================")
    print(f"result={payload.get('result')}")
    print(f"calendar={payload.get('calendar_version')}")
    print(f"eligibility={(payload.get('eligibility') or {}).get('aggregate')}")
    print(f"research_eligible={(payload.get('eligibility') or {}).get('any_research_eligible')}")
    print()
    print("Calendar coverage:")
    for row in payload.get("calendar_coverage") or []:
        print(
            f"  {row.get('symbol')}: expected={row.get('expected_sessions')} "
            f"observed={row.get('observed_sessions')} missing={row.get('missing_sessions')} "
            f"unexpected={row.get('unexpected_sessions')} edge_before={row.get('edge_before_count')}"
        )
    print()
    print("CA:")
    for row in (payload.get("corporate_actions") or {}).get("table") or []:
        print(
            f"  {row.get('symbol')}: events={row.get('events')} known={row.get('known')} "
            f"unknown={row.get('unknown')} types={row.get('types')}"
        )
    br = payload.get("baseline_regression") or {}
    print()
    print(f"Baseline: result={br.get('result')} accepted={br.get('accepted_count')} trials={br.get('trial_count')}")
    print(f"Leakage: {br.get('leakage')}")
    print(f"Reproducibility: {br.get('reproducibility')}")
    s = payload.get("safety") or {}
    print(
        f"Safety: orders={s.get('orders_submitted')} place_order={s.get('place_order_called')} "
        f"live={s.get('live_trading')} paper={s.get('paper_trading')} kill={s.get('kill_switch')}"
    )
    print()
    print(payload.get("statement"))
    print("NO PAPER OR LIVE TRADING WAS STARTED.")
    print("==================================================")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
