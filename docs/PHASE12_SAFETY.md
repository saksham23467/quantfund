# Phase 12 — Safety

## Hard rules

1. No live order submission; no KiteConnect `place_order`; no broker order API.
2. Paper path may only inject `PaperExecutionAdapter`.
3. `PaperActivationRecord` always sets `LIVE_TRADING=FALSE` and `paper_only=true`.
4. Live `production.activation` must not authorize paper; paper must not create live activation.
5. Research eligibility gates are not weakened; DEVELOPMENT_ONLY ≠ RESEARCH_ELIGIBLE.
6. Controlled paper eligibility never implies research validity, profitability, or live readiness.
7. RiskEngine / PaperRiskEngine cannot be bypassed.
8. Kill switch TRIGGERED rejects new orders; restart must restore triggered state (no silent reset).
9. Reconciliation mismatch ⇒ `allows_new_orders=FALSE`; no automatic repair.
10. UNKNOWN membership never tradable.
11. RAW OHLC never modified; no automatic merger/demerger price reconstruction.
12. No fabricated bars; no silent forward-fill.
13. No automatic strategy enablement from campaigns/AI/acceptance.
14. Credentials never stored in source, registry, reports, journals, or logs (redacted).

## Isolation tests

- Static import scan of `phase12` modules for forbidden live/order modules
- Runtime injection of fake live adapters must raise
- After any Phase 12 demo/session: `live_orders == 0`

## Claims

Phase 12 may claim only that **simulated** paper machinery ran under controlled gates.
It must not claim research-grade validation or live readiness.
