# Phase 14 — Real-Time Paper / Shadow Market Validation

## Purpose

Consume market data **as it becomes available** and run **simulated** paper
or **shadow** observation. This is **not** live trading.

Mode labels:

- `REAL_TIME_PAPER` — simulated fills + portfolio updates via `PaperExecutionAdapter`
- `SHADOW` — signals/orders/risk recorded as `WOULD_*`; no portfolio mutation
- Neither mode may call a broker

## Reuse

| Layer | Source |
|-------|--------|
| Paper fills | `PaperExecutionAdapter` / `PaperSession` |
| Eligibility | Phase 12 controlled simulation gates + activation |
| Journal / CA / portfolio | Phase 13 patterns |
| Features | `FeatureEngine` as-of(T) |
| Calendar | Existing NSE / Fake calendar providers |
| Strategies | Existing baselines only |

## Flow

```
RealTimeMarketDataProvider.next_bar()
  → freshness / session gate
  → FeatureEngine (≤ T)
  → Strategy signal
  → RiskEngine
  → SHADOW: WOULD_ORDER / WOULD_FILL
     or PAPER: PaperExecutionAdapter → fill → portfolio
  → journal + reconciliation + health
```

## Data reality

`YFinanceSimulationMarketDataProvider` is a **polling / simulation** source:

- `source_grade = non_exchange`
- `research_eligible = false`
- `simulation_only = true`

Demo uses a deterministic simulated stream so CI does not require the market to be open.

## Out of scope

Live broker order submission, live activation, LLM/genetic search, Phase 15.
