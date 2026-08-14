# Phase 15 — Operations

```bash
make phase15-preflight
make phase15-demo          # simulated fallback; no credentials required
make phase15-connectivity  # read-only only; skips if unconfigured
make phase15-shadow
make phase15-report
```

## Without credentials

Demo uses simulated market data + simulated read-only broker.
Expected: Phase 15 PASS, Real orders 0, Claims NONE.

## With credentials

`phase15-connectivity` may probe authenticated **read-only** endpoints.
It must never place, cancel, or modify orders.

## Failure behavior

- Provider disconnect / stale → pause shadow decisions
- Broker read failure → degrade; do not trade
- Reconcile mismatch → block new shadow orders
- Kill switch → block decisions
- Config/strategy hash change mid-session → SESSION_INVALIDATED

## Recovery

Load journal + checkpoint; refuse trading if untrusted; no duplicate WOULD_*.
