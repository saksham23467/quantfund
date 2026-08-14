# Phase 11 — Safety

## Hard rules

1. No live order submission.
2. No production broker order API calls from paper runner.
3. No automatic live activation / activation records for live trading.
4. No weakening of research eligibility.
5. No bypassing risk limits or kill switch.
6. No StrategySpec self-acceptance.
7. No AI-generated arbitrary code.
8. No TEST / future-data leakage.
9. No RAW OHLC or historical dataset mutation.
10. No automatic merger/demerger price reconstruction.
11. UNKNOWN membership never tradable.
12. DEVELOPMENT_ONLY never becomes RESEARCH_ELIGIBLE.
13. Paper mode explicitly distinct from live.

## Live isolation

`PaperTradingSession` constructor accepts only `PaperExecutionAdapter`.  
Passing any other adapter type fails closed.

AST/import tests ensure phase11 paper runner modules do not import Zerodha `place_order` submission paths for live use. Connectivity may use read-only helpers only.

## Credentials

From environment only. Never in git, experiments, registry, reports, or logs. Always redacted.

## Fail closed

Broker disconnect, auth failure, missing/stale data, UNKNOWN membership, risk/kill switch, reconcile mismatch, invalid dataset checksum, development-only dataset, attempt to invoke live execution → **no new paper orders** (and never live orders).

## Claims

Paper profitability ≠ strategy acceptance.  
Paper pass ≠ live authorization.  
Do not claim the system is safe for live trading because paper works.
