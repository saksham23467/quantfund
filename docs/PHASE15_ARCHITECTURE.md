# Phase 15 — Real Market Data + Broker Shadow Integration

## Goal

Consume **real or simulated** market data and connect a **read-only** broker
adapter for account observation, while producing only:

- `WOULD_ORDER`
- `WOULD_FILL` / `SIMULATED_ORDER` (optional local simulation)
- never `REAL_ORDER`

Live trading remains **DISABLED**. `place_order` is unreachable from Phase 15.

## Plan (reuse, do not duplicate)

| Need | Reuse |
|------|--------|
| Shadow decisions | Phase 14 `ShadowEngine` |
| Simulated stream fallback | `YFinanceSimulationMarketDataProvider` |
| RT loop / freshness / session | Phase 14 realtime + session + health |
| Paper activation (not live) | Phase 12 `PaperActivationRecord` |
| Instrument identity | `data/instruments/resolve.py`, `data/identity.py` |
| Zerodha read connectivity patterns | `production/connectivity.py` GuardTransport ideas |
| Journal / recovery | Phase 13/14 journal + checkpoint patterns |

## New Phase 15 layers

```
RealTimeMarketDataProvider (existing ABC)
  + MarketDataCapabilities / provenance
  + RealMarketEventValidator
  + Simulated fallback | configured real adapter stub

ReadOnlyBrokerAdapter (NEW)
  + BrokerCapabilities(place_order=FALSE, ...)
  + SimulatedReadOnlyBroker | configured read-only wrapper

ShadowSession (NEW)
  + freeze strategy/spec/risk/feature hashes
  + state machine CREATED→…→COMPLETED / FAILED_SAFE
  + WOULD_* via ShadowEngine
  + optional broker position reconcile (read-only)
```

## Conflicts / resolutions

1. **Phase 14 forbids Zerodha imports** → Phase 15 is a separate package; demo CI uses simulated providers only.
2. **Paper gate blocks broker credentials on execution** → credentials only for read-only data-plane adapters, never passed to paper execution.
3. **`BrokerExecutionAdapter.place_order` required by ABC** → Phase 15 uses a **narrow** `ReadOnlyBrokerAdapter` without write methods.

## Out of scope

Live trading, place/cancel/modify order, LLM, genetic search, Phase 16.
