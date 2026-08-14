# Phase 10 — Production Readiness & Controlled Zerodha Activation

**Status:** Production-readiness layer (this document).  
**Companion:** `PHASE10_ARCHITECTURE.md` (research → paper evidence; unchanged).  
**Does not enable:** unrestricted live trading, automatic order placement, LLM/genetic search.

## Objective

Prove QuantFund can safely operate **around** a broker without accidental orders, and that every live capability requires **explicit human authorization**.

This is **not** “turn on live trading.”

## Architecture (additive)

```text
Preflight → Health → Dry-run → E2E replay (mock)
                ↓
        ActivationGates (ALL required)
                ↓
        Canary readiness (limits only; no auto-order)
                ↓
        BROKER_LIVE still DEFAULT DISABLED
```

Existing Phase 9B components reused:

- `brokers/zerodha` adapter
- `ExecutionRouter` + `LiveExecutionGuard`
- `BrokerReconciler`
- `KillSwitch` (+ layered production controls)

## Preflight

`quantfund.production.preflight` returns structured `PASS | WARN | FAIL | NOT_CONFIGURED`.  
Preflight never places, modifies, or cancels orders.

## Read-only connectivity

`make zerodha-connectivity-test` may authenticate and read profile/instruments/quotes **only if credentials are configured**.  
Never submits orders. Secrets never printed.

## Order dry-run

`make zerodha-order-dry-run` shows the exact broker request that **would** be sent. Visually distinct from a real order. No submission.

## Activation gates (ALL required)

| Gate | Meaning |
|------|---------|
| LIVE_TRADING_ENABLED | Explicit activation record present & valid |
| BROKER_CREDENTIALS_VALID | Credentials loadable for target env |
| BROKER_CONNECTIVITY_VALID | Health/connectivity OK |
| PREFLIGHT_VALID | No FAIL checks |
| RECONCILIATION_CLEAN | Last reconcile matched |
| RISK_CONFIG_VALID | Limits configured |
| HUMAN_CONFIRMATION | Confirmation phrase + actor (not env-alone) |
| STRATEGY_EXPLICITLY_ENABLED | Strategy id/hash approved |
| GLOBAL_KILL_SWITCH_OFF | Kill switch armed (not triggered) |

Any failure ⇒ **NO ORDER**. Default: `BROKER_LIVE = DISABLED`.

## Human confirmation

`make enable-live-trading` requires an explicit confirmation phrase and records activation metadata.  
It does **not** place orders. Env vars alone cannot authorize live trading.

## Canary

Extremely small explicit limits. Does not bypass risk. Does not auto-submit canary orders.  
Readiness command reports capability only.

## Invariants

- Research eligibility gates untouched
- yfinance / historical CA remain DEVELOPMENT_ONLY unless independently certified
- StrategySpec / ResearchRunner / generators cannot submit broker orders
- Paper kernel independent
- CI/demos/tests: **zero** real Zerodha orders
