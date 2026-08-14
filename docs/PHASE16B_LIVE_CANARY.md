# Phase 16B — Live Canary

## Modes

| Mode | place_order | When |
|------|-------------|------|
| CANARY_SIMULATION | Mock only; `live_orders=0` | Demo / CI |
| LIVE_CANARY | Real only if all gates pass | Explicit `make phase16b-live-canary` |

## ActivationRecord (required)

Immutable record: strategy id/version/hash, config hashes, broker, account hash,
capital + risk ceilings, timestamps, expiry, human confirmation phrase,
activation nonce, configuration hash.

Phrase: `I_CONFIRM_CONTROLLED_LIVE_CANARY`

## Canary policy (tiny defaults)

- max order qty: 1
- max order value: ₹1,000
- max position value: ₹2,000
- max daily loss: ₹500
- max orders/day: 2
- max turnover/day: ₹2,000
- single strategy allowlist
- small instrument allowlist

## Commands

```bash
make phase16b-demo          # mock; never real orders
make phase16b-preflight     # all checks; no place_order
make phase16b-live-canary   # dangerous; requires LIVE_TRADING=true + activation
```
