# Phase 12 — Controlled Paper Trading Activation

## Status

Phase 11 certified the paper *machinery* (FSM, journal, isolation, replay harness)
but demos stayed non-tradable (`orders=0`) because research→paper eligibility
requires `RESEARCH_ELIGIBLE` and no licensed package is configured.

Phase 12 activates a **controlled simulation paper path** that can produce
non-zero simulated orders/fills while:

- Research eligibility remains `DEVELOPMENT_ONLY`
- Live trading remains `DISABLED`
- No Zerodha / broker order API is reachable from the paper path
- Claims remain `NONE` regarding research-grade validity

## Audit summary (reuse, do not duplicate)

| Component | Location | Phase 12 role |
|-----------|----------|---------------|
| Strategy loop + next-bar-open | `paper/session.py` `PaperSession` | **Primary execution kernel** |
| Fill factory | `paper/execution.py` `PaperExecutionAdapter` | Sole fill creator |
| Risk + kill switch | `paper/risk.py`, `paper/kill_switch.py` | Authoritative; not bypassed |
| Reconciliation | `paper/reconciliation.py` | Fail closed |
| Research→paper gate | `paper/eligibility.py` `PaperEligibilityGate` | **Unchanged** (still blocks DEVELOPMENT_ONLY) |
| Phase 11 FSM/journal/isolation | `phase11/*` | Journal, reports, drift, isolation reused |
| yfinance provider | `data/providers/yfinance_provider.py` | Wrapped as paper market-data source (non_exchange) |
| Corporate actions | `data/corporate_actions/*` | Existing CA model remains authoritative |
| Live activation | `production/activation.py` | **Forbidden** on paper path |

## Architectural resolution (not a conflict)

Phase 8/10/11 policy:

```
DEVELOPMENT_ONLY  ⇒  research_paper_eligible = FALSE
```

Phase 12 **does not weaken** that gate. It introduces a **separate** concept:

```
controlled_simulation_paper_eligible
```

which may be `TRUE` when all Phase 12 simulation gates pass (including an explicit
human paper-activation record with `LIVE_TRADING=FALSE`), even if research
eligibility is `DEVELOPMENT_ONLY`.

Reporting:

| Field | Meaning |
|-------|---------|
| `research_eligibility` | From package certification (`DEVELOPMENT_ONLY` without licensed package) |
| `research_paper_eligible` | Existing `PaperEligibilityGate` result (still false on DEVELOPMENT_ONLY) |
| `paper_eligible` / `controlled_paper_eligible` | Phase 12 controlled-simulation gate |

Paper results on yfinance/fixtures are **not** research evidence and **not**
live-trading readiness.

## Desired flow

```
Market Data (fixture | yfinance development)
    → PaperMarketDataAdapter (validate; Asia/Kolkata; fail closed)
    → Calendar / session check
    → CA context (existing infrastructure; RAW OHLC untouched)
    → Strategy / StrategySpec
    → Signal
    → PaperRiskEngine
    → OrderIntent (scheduled next bar)
    → PaperExecutionAdapter (RAW open ± slippage + costs)
    → Fill → Portfolio
    → PaperJournal
    → Reconciliation
    → Report / Drift
```

Forbidden:

```
Strategy → Zerodha → real order
```

## Gaps filled by Phase 12

1. Runnable driver producing `orders > 0` and `fills > 0` under controlled paper eligibility
2. Explicit paper activation record (`paper_only=true`, `LIVE_TRADING=FALSE`)
3. Session-facing market-data adapter (offline fixture preferred; yfinance optional network)
4. Journal-backed restart/recovery (restore kill switch, positions, refuse if untrusted)
5. Make targets: `phase12-preflight|paper|replay|report|demo`
6. ≥60 Phase 12 tests including live isolation

## Package layout

```
src/quantfund/phase12/
  eligibility.py      # ControlledSimulationPaperGate
  activation.py       # PaperActivationRecord (not live ActivationRecord)
  market_data.py      # PaperMarketDataAdapter
  engine.py           # ControlledPaperEngine (wraps PaperSession)
  recovery.py         # Restart from journal/state snapshot
  isolation.py        # Extend Phase 11 isolation
  reports.py          # Session + safety + drift packaging
  ca_context.py       # Thin bridge into existing CA as-of helpers
```

## Safety invariants (unchanged)

1. DEVELOPMENT_ONLY ≠ RESEARCH_ELIGIBLE
2. Next-bar-open; no same-bar fills; RAW execution prices
3. Strategy/generator never create fills
4. Paper path injects only `PaperExecutionAdapter`
5. Risk engine + kill switch fail closed
6. Reconciliation mismatch ⇒ `allows_new_orders=FALSE`
7. No live activation records; no place_order
8. No automatic strategy/paper/live enablement
9. yfinance remains `source_grade=non_exchange`

## Out of scope (Phase 13+)

- Live broker order submission
- Live activation
- Promoting yfinance to research-eligible
- Weakening `PaperEligibilityGate`
