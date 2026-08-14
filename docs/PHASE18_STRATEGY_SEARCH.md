# PHASE 18 — Controlled Strategy Research

## Status

Controlled fixed-grammar search over certified Zerodha historical packages.
**No live trading. No paper trading. Broker writes disabled. Kill switch armed.**

## Dataset

- Combined hash: `sha256:588736f373856baf836c7d1a841a4057bef5675d33089d8409a562af50307a21`
- Symbols: RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, SBIN, ITC, LT
- Range: 2018-01-01 → 2026-08-12
- Eligibility: DEVELOPMENT_ONLY (unchanged)

## Search

- Mode: `demo`
- Config hash: `sha256:ffa186302aa5df86d0bc77946cedb8d1a19c9931798472723634ff0cfb938174`
- Candidates generated: 15
- Evaluated: 120
- Finalists: 5
- Accepted: 0
- Paper candidates: 0

## Ranking policy

- Parameters selected on TRAIN; candidates ranked on VALIDATION only
- TEST sealed until finalist evaluation
- Existing `score_policy_v1` + DEVELOPMENT_ONLY gates (no new thresholds)
- Trial family: `phase18_controlled_search` (counters not reset)

## Gates

| Gate | Result |
|------|--------|
| Leakage | PASS |
| Walk-forward | PASS |
| Robustness | PASS |
| DSR | PASS |
| Reproducibility | PASS |
| TEST seal | True |

## Artifacts

- `reports/phase18_strategy_search.json`
- `reports/phase18_leaderboard.json`
- Experiment registry under `experiments/phase18/registry/`

## Safety

- place_order_called = 0
- orders_submitted = 0
- broker_write_capability = DISABLED
- live_trading = DISABLED
- paper_trading = NOT_STARTED
- kill_switch = ARMED
