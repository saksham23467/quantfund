# Real Market Data (Phase 15)

## What is real vs simulated

| Mode | When | Grade |
|------|------|-------|
| SIMULATED stream | Default / CI / no provider configured | `non_exchange`, development |
| REAL_READ_ONLY | Explicit provider config + credentials where needed | Declared by provider contract; not auto research-eligible |

yfinance remains **DevelopmentProvider / simulation-only**. It is never
reclassified as exchange-grade because Phase 15 exists.

## Provider contract

Every provider must declare:

- `provider_id`
- `source_grade`
- `exchange`
- `timezone`
- `timestamp_semantics`
- realtime / historical capabilities
- instrument identity approach
- license/provenance status

## Validation before strategy

Symbol identity, timestamp/TZ, monotonic order, duplicates, stale, OHLC,
volume, session/calendar, interval. Failures → `DATA_BLOCKED` (no decision).
