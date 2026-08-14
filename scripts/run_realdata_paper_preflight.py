#!/usr/bin/env python3
"""Real-market-data PAPER trading preflight (NOT live). STOPS before any session.

DATA_SOURCE=ZERODHA  EXECUTION_MODE=PAPER  BROKER_WRITES=DISABLED
No broker orders, place_order unreachable, kill switch ARMED.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.paper_realdata.preflight import run_realdata_paper_preflight  # noqa: E402
from quantfund.paper_realdata.report import write_preflight_reports  # noqa: E402


def main() -> int:
    payload = run_realdata_paper_preflight()
    json_path = ROOT / "reports" / "realdata_paper_preflight.json"
    md_path = ROOT / "docs" / "REALDATA_PAPER_TRADING.md"
    write_preflight_reports(payload, json_path=json_path, md_path=md_path)

    mode = payload["mode"]
    r = payload["report"]
    print("==================================================")
    print("REAL-MARKET-DATA PAPER TRADING — PREFLIGHT (NOT LIVE)")
    print(f"DATA_SOURCE     = {mode['DATA_SOURCE']}")
    print(f"EXECUTION_MODE  = {mode['EXECUTION_MODE']}")
    print(f"BROKER_WRITES   = {mode['BROKER_WRITES']}")
    print("--- preflight report ---")
    print(f"zerodha_data_connected     = {str(r['zerodha_data_connected']).lower()}")
    print(f"strategy_accepted          = {str(r['strategy_accepted']).lower()}")
    print(f"paper_execution_enabled    = {str(r['paper_execution_enabled']).lower()}")
    print(f"real_broker_writes_enabled = {str(r['real_broker_writes_enabled']).lower()}")
    print(f"kill_switch                = {r['kill_switch']}")
    print(f"orders_submitted           = {r['orders_submitted']}")
    print(f"place_order_called         = {r['place_order_called']}")
    print("--- verdict ---")
    print(f"can_start_paper_session    = {str(payload['can_start_paper_session']).lower()}")
    print(f"started_paper_session      = {str(payload['started_paper_session']).lower()}")
    print(f"stop_reason                = {payload['stop_reason']}")
    if payload["blockers"]:
        print("--- blockers ---")
        for b in payload["blockers"]:
            print(f"  [BLOCKED] {b}")
    print(f"report_json = {json_path}")
    print("==================================================")
    print("STOP: preflight only — no paper session was started.")

    # Hard safety invariants (fail the process if ever violated).
    assert r["real_broker_writes_enabled"] is False, "real broker writes must be DISABLED"
    assert r["orders_submitted"] == 0, "orders_submitted must be 0"
    assert r["place_order_called"] == 0, "place_order_called must be 0"
    assert r["kill_switch"] == "ARMED", "kill switch must be ARMED"
    assert payload["started_paper_session"] is False, "no session may be started"
    assert payload["safety"]["live_trading"] == "DISABLED"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
