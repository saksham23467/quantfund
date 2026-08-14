# Phase 9 Execution Safety

Phase 9 v1 implements an **execution gateway** with **MockBroker** and **DRY_RUN** only.

## What Phase 9 v1 does **not** enable

- Real broker SDKs or exchange APIs
- Real order submission / network execution paths
- Real credentials consumption
- Automatic paper → live promotion
- Automatic emergency position flattening
- Limit orders, short selling, leverage, options, futures
- `LIVE_SEND` mode

**Real orders sent must remain 0.**

## Hard rules

| Rule | Enforcement |
|------|-------------|
| Mock only | `assert_mock_only` / `ALLOWED_BROKER_ADAPTER_IDS` |
| DRY_RUN only | `ExecutionMode` has a single value; other modes raise |
| UNKNOWN ≠ FILLED | Reconciliation + retry guards |
| No blind retry | `IdempotencyStore.can_retry` |
| DEVELOPMENT_ONLY → LIVE_BLOCKED | `LiveTradingEligibilityGate` |
| Kill switch = freeze only | Blocks new orders; no flatten API |
| Secrets | Env refs only; redacted from audit |

## Authorization ladder

```
RESEARCH_ELIGIBLE
    → PAPER_EVIDENCE
    → LIVE_TRADING_ELIGIBLE
    → OPERATOR_APPROVED
    → EXECUTION (DRY_RUN in v1)
```

No rung may be skipped. Campaign acceptance or paper eligibility alone is insufficient.

## Strategy isolation

Strategies must not import `quantfund.execution` broker/credential modules.
Paper fills remain owned by `PaperExecutionAdapter`.
Backtest next-bar-open semantics are unchanged.
