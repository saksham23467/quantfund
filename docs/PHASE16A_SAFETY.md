# Phase 16A — Safety

1. Live trading always DISABLED; readiness ends `LIVE_TRADING_DISABLED`.
2. Live orders = 0; order submission = NOT IMPLEMENTED.
3. Write-capable broker capabilities fail closed.
4. Kill switch remains ARMED by default and is mandatory for any future live path.
5. Reconciliation mismatch blocks future order submission (and readiness fails closed).
6. Stale data / clock skew → health FAIL; no progression toward live.
7. Secrets never appear in logs, reports, exceptions, tests, or artifacts.
8. Research eligibility remains DEVELOPMENT_ONLY (gates unchanged).
9. yfinance stays development/simulation — not live-grade.
10. Phase 16A AST/isolation proves no `place_order` call sites.
11. CI never contacts Zerodha (mock transport only).
12. No StrategySpec / next-bar-open / eligibility weakening.
