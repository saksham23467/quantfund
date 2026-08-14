# PHASE 21 — Autonomous Real-Time Paper Trading Qualification

**Result:** `PAPER_INSUFFICIENT_ACTIVITY`

========================================
LIVE_TRADING = DISABLED
BROKER_WRITE = DISABLED
PAPER_TRADING = ENABLED
KILL_SWITCH = ARMED
========================================

## Distinctions

- **PAPER_ORDER** — simulated via `PaperExecutionAdapter` only
- **LIVE_BROKER_ORDER** — forbidden; count must remain 0

## Strategy

- name: `mean_reversion`
- strategy_hash: `97c2381b45b89db0`
- configuration_hash: `608c62ca29e261d7`
- PAPER_CANDIDATE: `False`
- reason: development_only_dataset_cannot_be_paper_eligible;certified_eligibility=development_only insufficient for paper;missing_acceptance_evidence_id;infrastructure_sandbox_cannot_be_paper_eligible
- mode: `OBSERVATION_PAPER_SANDBOX`

## Runtime

- EC2 instance: `quantfund-live`
- Zerodha data source: `zerodha_mock_test_only`
- trading days: 20
- market events: 60
- signals: 57
- paper orders: 0
- paper fills: 0
- risk rejections: 0

## Performance (informational — not a live-trading gate)

- P&L: 0.0
- drawdown: 0.0
- Sharpe: None
- turnover: 0.0
- fees: 0
- slippage: 0

## Drift / Recovery

- backtest-paper drift: `FLAG`
- restarts: 0
- recovery events: 0
- outages: 0
- reconciliation: `CLEAN`

## Safety

- leakage: `NONE_DETECTED`
- reproducibility: `checkpoint_recovery_ok`
- broker write calls: `0`
- live orders: `0`
- kill switch: `ARMED`

## No-trade diagnostics

```json
{
  "total_market_events": 60,
  "total_strategy_evaluations": 57,
  "BUY_signals": 0,
  "SELL_signals": 0,
  "HOLD_signals": 57,
  "risk_approved_signals": 0,
  "risk_rejected_signals": 0,
  "paper_orders": 0,
  "paper_fills": 0,
  "symbols_evaluated": [
    "RELIANCE"
  ],
  "bars_evaluated": 60,
  "strategy_evaluation_errors": 0,
  "PAPER_CANDIDATE": false,
  "mode": "OBSERVATION_PAPER_SANDBOX",
  "why_no_activity": [
    "PAPER_CANDIDATE=FALSE \u2014 running OBSERVATION/PAPER-SANDBOX only",
    "only_HOLD_signals_no_actionable_buy_sell",
    "no_risk_approved_signals_so_no_paper_orders"
  ],
  "signal_reason_counts": {
    "signal_HOLD_no_order_intent": 57,
    "no_signal_session_or_kill": 3
  },
  "note": "Do NOT simply report PAPER_VALIDATED. Zero activity must be explained."
}
```

## Blockers

- (none)

_Generated 2026-08-12T20:06:13.689484+00:00_
