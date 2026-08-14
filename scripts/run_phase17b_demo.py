#!/usr/bin/env python3
"""Phase 17B full demo: download multi-year REAL data + re-run Phase 17A validation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17b.pipeline import run_phase17b_validation, write_phase17b_docs


def main() -> int:
    # Force download attempt for REAL expansion (immutable new versions)
    payload = run_phase17b_validation(
        download=True,
        force_mock=False,
        skip_download_if_packages=False,
    )
    write_phase17b_docs(payload, ROOT / "docs" / "PHASE17B_DATASET_EXPANSION.md")

    print("==================================================")
    print("QUANTFUND PHASE 17B")
    print("EXPAND REAL ZERODHA HISTORICAL DATASET")
    print("==================================================")
    print(f"result={payload.get('result')}")
    print(f"data={(payload.get('download') or {}).get('data')}")
    print(f"download_status={(payload.get('download') or {}).get('status')}")
    print()
    print("Packages:")
    for p in payload.get("packages") or []:
        print(
            f"  {p.get('symbol')}: bars={p.get('bars')} "
            f"{p.get('start')}→{p.get('end')} hash={p.get('content_hash')}"
        )
    print()
    print("Leaderboard (VALIDATION):")
    for r in payload.get("leaderboard") or []:
        print(
            f"  {r.get('strategy')}: oos={r.get('mean_oos_return')} "
            f"sharpe={r.get('mean_sharpe')} dd={r.get('mean_max_dd')} "
            f"accepted={r.get('accepted')}"
        )
    print()
    print(f"Walk-forward: {(payload.get('walk_forward') or {}).get('status')}")
    print(f"Robustness: {(payload.get('robustness') or {}).get('status')}")
    print(f"Leakage: {(payload.get('leakage') or {}).get('status')}")
    print(f"Reproducibility: {(payload.get('reproducibility') or {}).get('status')}")
    print(f"Trial count: {payload.get('trial_count')} family={payload.get('trial_family_id')}")
    print(f"Accepted: {(payload.get('acceptance') or {}).get('accepted_count')}")
    print(f"PAPER_CANDIDATE: {(payload.get('paper_candidates') or [{}])[0]}")
    print(f"Eligibility: {payload.get('eligibility')}")
    s = payload.get("safety") or {}
    print(
        f"Safety: orders={s.get('orders_submitted')} place_order={s.get('place_order_called')} "
        f"live={s.get('live_trading')} kill={s.get('kill_switch')}"
    )
    print()
    print(payload.get("statement"))
    print("==================================================")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
