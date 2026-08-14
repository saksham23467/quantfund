# Paper Validation (Phase 10)

## What paper validation means

Paper validation produces **evidence** that a research-accepted strategy behaved
acceptably under the Phase 8 paper kernel with production eligibility gates.

It does **not** mean:

- the strategy is profitable
- live trading is authorized
- real broker orders may be sent

## Requirements for `paper_eligible=true`

1. Dataset certified `RESEARCH_ELIGIBLE` or `PRODUCTION_CANDIDATE`
2. Immutable `StrategyAcceptanceRecord` (`acceptance_evidence_id`)
3. Sealed TEST completed
4. Robustness passed
5. Walk-forward requirements satisfied
6. DSR / trial accounting valid
7. No leakage / no UNKNOWN membership traded
8. Valid risk + execution configuration
9. Operator-controlled paper session
10. Session mode is **not** `infrastructure_sandbox`

`DEVELOPMENT_ONLY` always yields `paper_eligible=false`.

## Paper evidence

Built from Phase 8 `PaperSessionResult` + audit/reconciliation (not a parallel ledger).

## `paper_policy_v1`

Versioned thresholds (duration, trades, drawdown, recon, drift/divergence, etc.).

- Verdict `PASSED` → may set `LIVE_ELIGIBILITY_CANDIDATE`
- Still: **live trading DISABLED**
- Positive paper P&L alone is insufficient

## Session state machine

```text
CREATED → ELIGIBILITY_CHECKED → READY → RUNNING → RECONCILING
→ COMPLETED → EVALUATED → PASSED | FAILED
```

Safety violations fail closed. No transition to live.
