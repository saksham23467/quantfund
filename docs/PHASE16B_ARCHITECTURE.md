# Phase 16B — Controlled Live Canary Execution

## Prominence

**This system is capable of submitting real broker orders only when the
explicit live-canary activation gates are satisfied. Normal demos, tests, CI,
paper, and shadow sessions never submit real orders.**

## Goal

Tightly controlled LIVE CANARY path through Zerodha/Kite. Not unrestricted
autonomous trading.

## Flow

```
Market Data → Strategy → Signal → Risk Engine
  → Live Pre-Trade Gate → Kill Switch → Reconciliation Gate
  → Canary Limits → Human Activation Record
  → ZerodhaCanaryBroker (extends Phase 16A) → Broker ack
  → Reconcile → Journal/Audit
```

## Reuse

| Concern | Source |
|---------|--------|
| Read-only Zerodha | `phase16a.ZerodhaReadOnlyBroker` (extended) |
| place_order HTTP | `brokers.zerodha.orders.place_order` |
| Idempotency | `brokers.intent_store.ExecutionIntentStore` |
| Production canary limits | `production.canary.CanaryLimits` / `canary_check_order` |
| Confirmation pattern | `production.activation.ACTIVATION_CONFIRM_PHRASE` |
| Kill switch | `paper.kill_switch.KillSwitch` |
| Position reconcile | `phase15.reconcile.reconcile_positions` |

## LIVE_TRADING flag

Default `false`. Environment alone never enables live trading.
Human ActivationRecord + confirmation phrase required.

## Out of scope

Unrestricted autonomy, AI mutation, genetic search, capital auto-scaling,
Phase 17.
