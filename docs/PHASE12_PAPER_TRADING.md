# Phase 12 — Paper Trading Operations Policy

## Two eligibility ladders

### A. Research → paper (Phases 8–11) — unchanged

Requires `research_eligible` / `production_candidate`, acceptance evidence, sealed TEST,
robustness, walk-forward, etc. **DEVELOPMENT_ONLY always fails this ladder.**

### B. Controlled simulation paper (Phase 12) — new

Allows paper *simulation* trading when:

1. Market-data provider configured (fixture or yfinance development)
2. Market data validates (timestamps, OHLC, stale, duplicates)
3. Calendar/session validation passes
4. Strategy explicitly enabled (`strategy_id` + version)
5. StrategySpec validation passes when a spec is supplied
6. Risk configuration valid
7. Kill switch armed and operational
8. `PaperExecutionAdapter` selected; live adapter absent
9. Broker credentials irrelevant / unavailable to execution
10. Reconciliation clean
11. Journal writable
12. Portfolio state restorable
13. Deterministic replay harness passes for the configured seed/events
14. No research/TEST acceptance path used as authorization shortcut
15. Explicit human `PaperActivationRecord` exists with `LIVE_TRADING=FALSE`

Result example:

```
Research eligibility: DEVELOPMENT_ONLY
research_paper_eligible: FALSE
controlled_paper_eligible / paper_eligible: TRUE
Live trading: DISABLED
Claims: NONE
```

## yfinance policy

- `source_grade = non_exchange`
- Never makes a dataset `RESEARCH_ELIGIBLE`
- Used only for development / controlled paper simulation
- Fail closed on stale, malformed, missing, or ambiguous data
- Never fabricate or silently forward-fill bars
- Do not claim real-time unless the provider guarantees it (yfinance does not)

## Execution

`signal(T) → order → next eligible session → RAW OPEN → simulated fill`

Costs and slippage models must be explicit (`cost_model_id`, `slippage_model_id`).
Unknown models fail closed.

## Partial fills

Phase 8 `PaperFillConfig` supports `ALLOW_PARTIAL`. Demo/default uses complete fills
(`ALL_OR_NOTHING`) unless configured otherwise.
