#!/usr/bin/env python3
"""Phase 19 controlled strategy research — gated behind research eligibility.

NO paper trading, NO live trading, NO broker orders, NO auto-promotion.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.research.strategy_research.runner import (  # noqa: E402
    run_phase19_strategy_research,
)


def main() -> int:
    payload = run_phase19_strategy_research()
    pre = payload["prerequisite"]
    f = payload["funnel"]
    print("==================================================")
    print("PHASE 19 CONTROLLED STRATEGY RESEARCH")
    print(f"research_eligible (prerequisite) = {str(pre['research_eligible']).lower()}")
    print(f"ran_search                       = {str(payload['ran_search']).lower()}")
    print(f"stopped_reason                   = {payload['stopped_reason']}")
    print("--- funnel ---")
    print(f"candidates tested                = {f['candidates_tested']}")
    print(f"candidates rejected              = {f['candidates_rejected']}")
    print(f"candidates passing validation    = {f['candidates_passing_validation']}")
    print(f"candidates passing OOS           = {f['candidates_passing_oos']}")
    print(f"candidates passing robustness    = {f['candidates_passing_robustness']}")
    print(f"candidates passing DSR           = {f['candidates_passing_dsr']}")
    print(f"final accepted candidates        = {f['final_accepted_candidates']}")
    print(f"dsr_trial_count                  = {payload['dsr_trial_count']}")
    print("auto_promotion                   = disabled")
    print("paper_trading / live_trading     = disabled")
    print("orders_submitted                 = 0")
    if pre["blockers"]:
        print("--- prerequisite blockers ---")
        for b in pre["blockers"]:
            print(f"  [UNMET] {b}")
    print("==================================================")
    if not payload["ran_search"]:
        print("STOP: research eligibility is FALSE — strategy research did not run.")
    elif f["final_accepted_candidates"] == 0:
        print("STOP: zero candidates accepted (valid result).")
    else:
        print("STOP after research (no auto-promotion).")

    safety = payload["safety"]
    assert safety["orders_submitted"] == 0
    assert safety["place_order_called"] == 0
    assert safety["live_trading"] == "DISABLED"
    assert payload["auto_promotion"]["enabled"] is False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
