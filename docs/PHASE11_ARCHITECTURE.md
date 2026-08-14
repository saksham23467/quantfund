# Phase 11 — Real Data + Paper Trading Certification

**Status:** Paper certification layer (this phase).  
**Does NOT enable:** live trading, real Zerodha order placement, automatic activation.

## Ladder

```text
RESEARCH_ELIGIBLE
        ↓
PAPER_ELIGIBLE
        ↓
PAPER TRADING (observation)
        ↓
CERTIFICATION / REPORTS
        ↓
ONLY A FUTURE PHASE MAY CONSIDER LIVE ACTIVATION
```

## Reuse map

| Need | Existing module |
|------|-----------------|
| Paper fills / next-bar-open | `paper.PaperExecutionAdapter` |
| Eligibility | `paper.PaperEligibilityGate` + research package certify |
| Risk | `paper.PaperRiskEngine` + `KillSwitch` |
| Session kernel | `paper.PaperSession` |
| Validation FSM (Phase 10) | `research.paper_session_fsm` |
| Drift / compare | `research.drift`, `research.backtest_paper_compare` |
| Read-only broker | `production.connectivity` |
| Preflight | `production.preflight` |

Phase 11 adds orchestration under `quantfund.phase11` — not a second broker/risk stack.

## Modes (never collapsed)

| Status | Meaning |
|--------|---------|
| `SIMULATED` | Fake broker/data for CI/demo |
| `CONNECTED_READ_ONLY` | Real credentials, read-only APIs only |
| `PAPER` | Paper execution path active |
| `LIVE` | Forbidden in Phase 11 |

## Research package

`QUANTFUND_RESEARCH_PACKAGE=/path` is inspected via Phase 7 certify machinery.  
Eligibility is **never** inferred from file presence alone.  
`DEVELOPMENT_ONLY` cannot become `RESEARCH_ELIGIBLE`.

## Paper ≠ Live

`PaperTradingSession` may only receive `PaperExecutionAdapter`.  
Live order submission adapters are architecturally rejected.
