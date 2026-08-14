# Phase 15 — Safety

1. LIVE_TRADING = FALSE always
2. REAL_ORDER count = 0 always
3. Broker submissions = 0 always
4. No `place_order` on Phase 15 path
5. Read-only broker cannot expose write methods
6. Kill switch ARMED by default
7. DEVELOPMENT_ONLY remains DEVELOPMENT_ONLY
8. Paper eligibility ≠ live eligibility
9. Stale / bad data → DATA_BLOCKED
10. Reconciliation mismatch → allows_new_shadow_orders = FALSE
11. Strategy/config hash freeze; mutation → SESSION_INVALIDATED
12. Secrets never logged

## Isolation tests

- Monkeypatch write methods → must never be called
- Static scan: Phase 15 must not import Zerodha `orders.place_order` for submission
- `can_place_orders` is False on all Phase 15 brokers
