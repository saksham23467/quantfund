# Phase 16B — Risk

Enforced **before every order** (any failure → no broker call):

- max order quantity / value
- max position value
- max daily loss (persisted across restarts)
- max orders/day / turnover/day
- allowed instruments / sides / product / order type
- stale market data / clock skew
- account + reconciliation CLEAN
- kill switch DISARMED for canary (re-arms on any failure)
- strategy allowlist + frozen hash match
- activation not expired
- LIVE_TRADING explicitly true (live mode only)
- yfinance rejected as live feed

Full account balance is never assumed available — only activation capital limit.
