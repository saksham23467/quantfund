# Phase 14 — Safety

## Hard rules

1. No `place_order` / broker submission from Phase 14
2. Only `PaperExecutionAdapter` may create fills (paper mode)
3. Shadow mode never mutates portfolio and never calls brokers
4. No live activation records
5. yfinance never becomes research-eligible
6. RiskEngine + kill switch + reconciliation fail closed
7. Stale data blocks new orders
8. No future bars in features/strategy
9. Next-bar-open preserved
10. Claims: NONE

## Broker isolation

Phase 14 modules must not import Zerodha order submission or
`production.activation`. Tests statically and dynamically enforce this.

## Report banner

```
MODE = REAL_TIME_PAPER or SHADOW
DATA SOURCE = YFINANCE / SIMULATED STREAM
RESEARCH ELIGIBILITY = DEVELOPMENT_ONLY
LIVE TRADING = DISABLED
BROKER SUBMISSIONS = 0
CLAIMS = NONE
```
