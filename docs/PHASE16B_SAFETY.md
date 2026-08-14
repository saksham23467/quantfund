# Phase 16B — Safety

**This system is capable of submitting real broker orders only when the
explicit live-canary activation gates are satisfied. Normal demos, tests, CI,
paper, and shadow sessions never submit real orders.**

1. `LIVE_TRADING=false` by default; env alone cannot enable.
2. Human confirmation phrase required; activation expires.
3. Kill switch ARMED by default; must be explicitly disarmed for canary;
   any failure re-arms; restart restores safe state.
4. Any gate failure → `place_order` never called.
5. Idempotent intents; crash recovery never blind-resubmits.
6. Reconciliation mismatch blocks new orders.
7. yfinance is not a live execution feed.
8. Research eligibility DEVELOPMENT_ONLY unchanged.
9. No AI strategy → live; no mutation; no arbitrary code execution.
10. No automatic canary → unrestricted live transition.
11. Secrets never logged.
12. CI uses MOCK only — never contacts Zerodha for orders.
