# Phase 16A — Real Broker Integration + Live Readiness

## Goal

Add a **read-only** Zerodha/Kite connectivity and live-readiness layer on top of
Phase 15. Final readiness outcome is always:

`LIVE_TRADING_DISABLED`

No real order submission. No `place_order` / `modify_order` / `cancel_order`.

## Reuse (do not duplicate)

| Concern | Source |
|---------|--------|
| Read-only broker ABC | `phase15.broker_readonly.ReadOnlyBrokerAdapter` |
| Write-capability fail-closed | `phase15.capabilities.BrokerCapabilities` |
| Position reconcile | `phase15.reconcile.reconcile_positions` |
| Kill switch | `paper.kill_switch.KillSwitch` |
| Guarded HTTP | `production.connectivity._GuardTransport` |
| Kite HTTP + Fake transport | `brokers.zerodha.client` |
| Portfolio reads | `brokers.zerodha.portfolio` |
| Creds from env | `brokers.zerodha.auth` |
| Secret redaction | `execution.credentials.redact_secrets` + `phase15.models.scrub_secrets` |

## New Phase 16A layers

```
Credentials (env only)
      ↓
GuardTransport (blocks order mutations)
      ↓
ZerodhaReadOnlyBroker (ReadOnlyBrokerAdapter)
      ↓
Connectivity health + Live readiness preflight
      ↓
BrokerConnectionSnapshot (immutable, no secrets)
      ↓
LIVE_TRADING_DISABLED  (always)
```

## Explicit non-goals

- Live order submission
- Parallel risk / eligibility / backtest engines
- AI / genetic search
- Promoting yfinance to live/research grade
- Weakening research eligibility gates
