# Phase 13 — Safety

## Hard prohibitions

1. No Zerodha / KiteConnect order placement
2. No live trading activation records
3. No LLM / genetic strategy generation
4. No weakening of research or live gates
5. No upgrading yfinance to research-eligible
6. No strategy-created fills
7. No future-bar visibility
8. No RAW OHLC mutation
9. No automatic merger/demerger price reconstruction
10. No silent fabrication / forward-fill of missing bars

## Fail-closed

- Duplicate / impossible OHLC → reject stream
- Stale / missing required data → no new orders
- Risk breach / kill switch → `allows_new_orders=false`
- Reconciliation mismatch → session FAILED
- Corrupted journal → recovery refused

## Claims

Reports must state:

```
RESEARCH ELIGIBILITY: DEVELOPMENT_ONLY
PAPER MODE: CONTROLLED HISTORICAL SIMULATION
LIVE TRADING: DISABLED
CLAIMS: NONE
```
