# PHASE 19 — Controlled Strategy Research

Phase 19 controlled strategy research. Gated behind research eligibility. NO PAPER TRADING, NO LIVE TRADING, NO BROKER ORDERS, NO AUTO-PROMOTION.

_Generated: 2026-08-12T19:37:27.252284+00:00_

## Prerequisite: research eligibility

- `research_eligible = false`
- `phase18_research_eligible = false`
- `pit_universe_research_eligible = false`
- `ran_search = false`
- `stopped_reason = research_eligibility_false`

### Prerequisite blockers

- `phase18_research_eligible=false(stopped_at=exchange_grade_source_certification)`
- `pit_universe:missing_pit_membership_ledger`
- `pit_universe:unknown_membership_sessions_gt_0`
- `pit_universe:instrument_identity_coverage_below_1.0`
- `pit_universe:delisted_coverage_insufficient`

## Funnel

| Stage | Count |
| --- | ---: |
| candidates tested | 0 |
| candidates rejected | 0 |
| candidates passing validation | 0 |
| candidates passing OOS | 0 |
| candidates passing robustness | 0 |
| candidates passing DSR | 0 |
| **final accepted candidates** | **0** |

DSR trial count (multiple-testing accounting): `0`

## Research budget

```json
{
  "candidates_consumed": 0,
  "experiments_consumed": 0,
  "max_candidates": 40,
  "max_experiments": 40
}
```

## Gate policy (inherited from campaign AcceptancePolicy; only stricter)

```json
{
  "dsr_min": 0.95,
  "max_oos_drawdown": 0.35,
  "min_oos_sharpe": 0.5,
  "min_trades": 1,
  "min_validation_sharpe": 0.5,
  "robustness_min_pass_rate": 0.5,
  "robustness_reject_if_fragile": true
}
```

## Auto-promotion

- enabled: `false`
- promoted candidates: `[]`
- Best strategy is never auto-promoted; acceptance != activation.

## Strategy families

- `trend_following`
- `momentum`
- `mean_reversion`
- `breakout`
- `volatility_regime`

## Safety

```json
{
  "broker_write_capability": "DISABLED",
  "kill_switch": "ARMED",
  "live_trading": "DISABLED",
  "ok": true,
  "orders_submitted": 0,
  "paper_trading": "NOT_STARTED",
  "place_order_called": 0,
  "statement": "NO PAPER OR LIVE TRADING WAS STARTED.",
  "write_scan_hits": []
}
```

## Result

Zero candidates accepted. This is a valid research result (fail closed). No strategy was promoted or traded.
