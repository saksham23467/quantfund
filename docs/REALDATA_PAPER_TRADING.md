# Real-Market-Data Paper Trading — Preflight

REAL-MARKET-DATA PAPER TRADING PREFLIGHT. NOT LIVE TRADING. No paper session was started. No broker order was submitted.

_Generated: 2026-08-12T19:47:37.341341+00:00_

## Mode

- `DATA_SOURCE = ZERODHA`
- `EXECUTION_MODE = PAPER`
- `BROKER_WRITES = DISABLED`

## Architecture

Zerodha market data -> market-data adapter -> strategy -> risk engine -> PaperExecutionAdapter -> simulated fills -> paper portfolio

## Preflight report

| Field | Value |
| --- | --- |
| zerodha_data_connected | false |
| strategy_accepted | false |
| paper_execution_enabled | true |
| real_broker_writes_enabled | false |
| kill_switch | ARMED |
| orders_submitted | 0 |
| place_order_called | 0 |

## Verdict

- `can_start_paper_session = false`
- `started_paper_session = false`
- `stop_reason = gates_not_satisfied_fail_closed`

### Blockers

- `zerodha_data_not_connected`
- `research_eligibility_false`
- `strategy_search_did_not_run`
- `zero_accepted_strategies`

## Gates NOT bypassed

- eligibility_gate
- strategy_acceptance_gate
- risk_limits
- kill_switch
- reconciliation
- stale_data_protection

## Broker-write guard

```json
{
  "can_place_orders": false,
  "execution_adapter": "PaperExecutionAdapter",
  "forbidden_write_methods_exposed": [],
  "live_gate_blockers": [
    "mode_not_broker_live",
    "live_confirm_phrase_missing",
    "risk_limits_not_configured",
    "broker_unhealthy",
    "strategy_not_broker_approved",
    "zerodha_env_not_production"
  ],
  "live_trading_gates_satisfied": false,
  "real_broker_write_capability": "ABSENT",
  "write_scan_hits": [],
  "write_scan_ok": true
}
```

## Safety

```json
{
  "broker_write_capability": "DISABLED",
  "cancel_order_called": 0,
  "kill_switch": "ARMED",
  "live_trading": "DISABLED",
  "modify_order_called": 0,
  "ok": true,
  "orders_submitted": 0,
  "paper_fills": 0,
  "paper_orders": 0,
  "paper_trading": "ENABLED",
  "place_order_called": 0,
  "statement": "PHASE 21 PAPER ONLY \u2014 ZERO LIVE BROKER ORDERS.",
  "write_scan_hits": []
}
```

**STOP — preflight only. No paper session was started.**
