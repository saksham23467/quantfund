# PHASE 17C — Research Dataset Certification & Data Quality Completion

Phase 17C dataset certification only. NO PAPER OR LIVE TRADING WAS STARTED.

- Result: `PASS`
- Calendar version: `nse_eq_v2018_2026_r1`
- Eligibility aggregate: `DEVELOPMENT_ONLY`
- Any RESEARCH_ELIGIBLE: `False`
- Zerodha shortcut: `False`
- Accepted strategies (baseline regression): `0`

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

## Calendar coverage (corrected multi-year NSE)

| Symbol | Expected | Observed | Missing | Unexpected | Edge before | In-window bars |
|---|---:|---:|---:|---:|---:|---:|
| RELIANCE | 2133 | 2134 | 6 | 7 | 0 | 2134 |
| TCS | 2133 | 2133 | 7 | 7 | 0 | 2133 |
| INFY | 2133 | 2133 | 7 | 7 | 0 | 2133 |
| HDFCBANK | 2133 | 2133 | 7 | 7 | 0 | 2133 |
| ICICIBANK | 2133 | 2133 | 7 | 7 | 0 | 2133 |
| SBIN | 2133 | 2133 | 7 | 7 | 0 | 2133 |
| ITC | 2133 | 2133 | 7 | 7 | 0 | 2133 |
| LT | 2133 | 2133 | 7 | 7 | 0 | 2133 |

## Corporate actions

| Symbol | Events | Known | Unknown/OTHER | Parse unknown | Coverage | Types |
|---|---:|---:|---:|---:|---|---|
| RELIANCE | 23 | 23 | 0 | 2 | PARTIAL | `{'dividend': 18, 'bonus': 3, 'rights': 1, 'demerger': 1}` |
| TCS | 77 | 77 | 0 | 8 | PARTIAL | `{'dividend': 70, 'bonus': 2, 'buyback': 5}` |
| INFY | 40 | 40 | 0 | 3 | PARTIAL | `{'dividend': 35, 'bonus': 3, 'buyback': 2}` |
| HDFCBANK | 22 | 22 | 0 | 1 | PARTIAL | `{'dividend': 19, 'split': 2, 'bonus': 1}` |
| ICICIBANK | 17 | 17 | 0 | 1 | PARTIAL | `{'dividend': 15, 'split': 1, 'bonus': 1}` |
| SBIN | 19 | 18 | 1 | 1 | PARTIAL | `{'dividend': 17, 'split': 1, 'other': 1}` |
| ITC | 27 | 27 | 0 | 1 | PARTIAL | `{'dividend': 24, 'bonus': 2, 'demerger': 1}` |
| LT | 25 | 25 | 0 | 2 | PARTIAL | `{'dividend': 21, 'bonus': 2, 'buyback': 2}` |


## Residual calendar gaps (explicit, not auto-repaired)

After extending to `nse_eq_v2018_2026_r1` and fixing IST session-date reload:

- Coverage ratio ≈ **0.997** (expected ≈2133 sessions for 2018-01-01→2026-08-12).
- Typical residual: **~6–7 missing** and **~7 unexpected** sessions per symbol.
- Missing dates include known special closures not in the holiday circular list (e.g. election-related: 2019-04-29, 2024-01-22, 2024-05-20, 2024-11-20).
- Unexpected dates include days our curated calendar marks closed but Zerodha returned a bar (e.g. 2023-06-28 Bakri Id date ambiguity vs 2023-06-29).
- These remain **quality ERROR**s under existing gates and contribute to RESEARCH_ELIGIBLE blockers — gates were **not** weakened.
- The previous `expected_sessions=743` bug (calendar only covering 2023–2025) is fixed.
- The previous `2017-12-31` edge bar was a **timezone reload artifact** (IST midnight → prior UTC day); with session-date preservation, packages start at **2018-01-01** and `edge_before_count=0`.

## Remaining blockers before strategy research (Phase 18)

- `capability_source_bar_ok=false (provider cannot satisfy research source bar)`
- `data_class=DEVELOPMENT_DATA cannot be research_eligible (development pipeline is permanently DEVELOPMENT_ONLY)`
- `delisted_coverage=unknown insufficient for research (need ['partial', 'complete'])`
- `instrument_identity_issues=2`
- `membership_coverage_ratio=0.0 < required 1.0`
- `quality ERROR count=13 codes=['bar_on_closed_session', 'missing_open_session']`
- `quality ERROR count=14 codes=['bar_on_closed_session', 'missing_open_session']`
- `source_grade=non_exchange is not exchange/paid research grade`
- `universe_completeness=current_snapshot_only (today's constituents must not stand in for history)`
- `unknown_membership_session_count=2133`
- `unknown_membership_session_count=2134`

## Baseline regression

- Result: `PASS`
- Trials: `270`
- Walk-forward: `{'enabled': True, 'config': {'train_sessions': 40, 'validation_sessions': 20, 'test_sessions': 20, 'step_sessions': 20, 'mode': 'rolling', 'anchored': False}, 'status': 'PASS'}`
- Robustness: `{'enabled': True, 'status': 'PASS'}`
- Leakage: `{'status': 'PASS', 'asof_matches_prefix': True, 'asof_stable_after_future_spike': True}`
- Reproducibility: `{'status': 'PASS', 'deterministic': True, 'result_hash_a': 'sha256:76267b3da2079b36945061de7e6eff3cc3e3b9b8cf8ceddd502ee55c539004c5', 'result_hash_b': 'sha256:76267b3da2079b36945061de7e6eff3cc3e3b9b8cf8ceddd502ee55c539004c5'}`

### Leaderboard

- `buy_and_hold`: oos=`0.39447462596469274` sharpe=`0.8443980431465217` accepted=`0`
- `mean_reversion`: oos=`-0.004124187227680209` sharpe=`0.13798620951153903` accepted=`0`
- `ma_cross`: oos=`0.3226421289126683` sharpe=`0.2429819216570548` accepted=`0`
- `momentum`: oos=`0.30452479031066815` sharpe=`0.14924990907555624` accepted=`0`
- `vol_breakout`: oos=`-0.09872794247503758` sharpe=`-0.6462422942403658` accepted=`0`

## Immutability

Phase 17B v1 packages are never overwritten; certified copies use next version.

**NO PAPER OR LIVE TRADING WAS STARTED.**
