# Phase 13 — Paper Validation Policy

## What is validated

Controlled historical simulation against the Milestone-1 backtest semantics:

- Signal at completed bar T
- Order after risk check
- Fill at next eligible bar RAW open ± slippage + costs
- No same-bar fills
- No future bars in strategy context

## Eligibility

| Field | Expected without licensed package |
|-------|-----------------------------------|
| Research eligibility | `DEVELOPMENT_ONLY` |
| Research→paper ladder | `FALSE` |
| Controlled simulation paper | `TRUE` after Phase 12 activation gates |
| Live trading | `DISABLED` |

Success of Phase 13 simulation **never** upgrades research eligibility.

## yfinance

- `source_grade = non_exchange`
- Simulation / development only
- Demo uses offline yfinance-**labeled** fixtures by default (CI-safe)
- Optional network fetch remains DEVELOPMENT_ONLY and fail-closed on errors

## Drift

Given identical dataset, strategy, params, calendar, CA policy, cost/slippage,
and capital:

`BacktestEngine` vs Phase 13 paper replay → expected `DRIFT = NONE`

Intentional differences (if any) must be documented; semantic violations are bugs.

## Multi-symbol

Per-symbol chronological streams with independent `seq` numbering preserve
next-bar-open. Interleaved global multi-symbol seq is not required for Phase 13
drift certification.
