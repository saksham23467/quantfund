# PHASE 17B — Expanded Real Zerodha Historical Dataset

Phase 17B historical expansion + revalidation only. No broker order submission occurred.

- Bundle/download status: `None`
- Trial family (continued): `phase17a_zerodha_baselines`
- Trial count after 17B: `225`

## Annual coverage (buy-and-hold diagnostic on RAW bars)

- `RELIANCE`: years=2017,2018,2019,2020,2021,2022,2023,2024,2025,2026
- `TCS`: years=2017,2018,2019,2020,2021,2022,2023,2024,2025,2026
- `INFY`: years=2017,2018,2019,2020,2021,2022,2023,2024,2025,2026
- `HDFCBANK`: years=2017,2018,2019,2020,2021,2022,2023,2024,2025,2026
- `ICICIBANK`: years=2017,2018,2019,2020,2021,2022,2023,2024,2025,2026
- `SBIN`: years=2017,2018,2019,2020,2021,2022,2023,2024,2025,2026
- `ITC`: years=2017,2018,2019,2020,2021,2022,2023,2024,2025,2026
- `LT`: years=2017,2018,2019,2020,2021,2022,2023,2024,2025,2026

## Stability checklist

### buy_and_hold
- profitable_across_multiple_years_data_present: `True`
- years_available: `['2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026']`
- profitable_across_multiple_stocks: `True`
- profitable_stock_count: `8`
- losing_stock_count: `0`
- survives_costs_slippage_robust_flag: `True`
- survives_walkforward_windows_present: `True`
- survives_robustness_not_fragile: `True`
- survives_dsr_accounted: `True`
- outperforms_buyhold_risk_adjusted_mean: `False`
- depends_heavily_on_one_stock: `False`
- single_stock_dependence_ratio: `0.2585247792433746`
- accepted_by_gates: `False`
- mean_oos_return: `0.39447462596469274`
- mean_sharpe: `0.8443980431465217`

### mean_reversion
- profitable_across_multiple_years_data_present: `True`
- years_available: `['2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026']`
- profitable_across_multiple_stocks: `True`
- profitable_stock_count: `4`
- losing_stock_count: `4`
- survives_costs_slippage_robust_flag: `False`
- survives_walkforward_windows_present: `True`
- survives_robustness_not_fragile: `False`
- survives_dsr_accounted: `True`
- outperforms_buyhold_risk_adjusted_mean: `False`
- depends_heavily_on_one_stock: `False`
- single_stock_dependence_ratio: `0.31744536399522605`
- accepted_by_gates: `False`
- mean_oos_return: `-0.004124187227680209`
- mean_sharpe: `0.13798620951153903`

### ma_cross
- profitable_across_multiple_years_data_present: `True`
- years_available: `['2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026']`
- profitable_across_multiple_stocks: `True`
- profitable_stock_count: `4`
- losing_stock_count: `4`
- survives_costs_slippage_robust_flag: `False`
- survives_walkforward_windows_present: `True`
- survives_robustness_not_fragile: `False`
- survives_dsr_accounted: `True`
- outperforms_buyhold_risk_adjusted_mean: `False`
- depends_heavily_on_one_stock: `False`
- single_stock_dependence_ratio: `0.3283941012449503`
- accepted_by_gates: `False`
- mean_oos_return: `0.3226421289126683`
- mean_sharpe: `0.2429819216570548`

### momentum
- profitable_across_multiple_years_data_present: `True`
- years_available: `['2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026']`
- profitable_across_multiple_stocks: `True`
- profitable_stock_count: `3`
- losing_stock_count: `5`
- survives_costs_slippage_robust_flag: `False`
- survives_walkforward_windows_present: `True`
- survives_robustness_not_fragile: `False`
- survives_dsr_accounted: `True`
- outperforms_buyhold_risk_adjusted_mean: `False`
- depends_heavily_on_one_stock: `False`
- single_stock_dependence_ratio: `0.3198007585156107`
- accepted_by_gates: `False`
- mean_oos_return: `0.30452479031066815`
- mean_sharpe: `0.14924990907555624`

### vol_breakout
- profitable_across_multiple_years_data_present: `True`
- years_available: `['2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026']`
- profitable_across_multiple_stocks: `False`
- profitable_stock_count: `1`
- losing_stock_count: `7`
- survives_costs_slippage_robust_flag: `False`
- survives_walkforward_windows_present: `True`
- survives_robustness_not_fragile: `False`
- survives_dsr_accounted: `True`
- outperforms_buyhold_risk_adjusted_mean: `False`
- depends_heavily_on_one_stock: `False`
- single_stock_dependence_ratio: `0.34511058894708274`
- accepted_by_gates: `False`
- mean_oos_return: `-0.09872794247503758`
- mean_sharpe: `-0.6462422942403658`

## Phase 17A vs 17B

See `reports/phase17b_comparison.json`.
- acceptance_stable_zero: `True`

# PHASE 17A — Real Zerodha Strategy Validation

## Prominence

Phase 17B historical expansion + revalidation only. No broker order submission occurred.

- Result: `PASS`
- Provider: `None`
- Data: `None`
- Combined dataset hash: `sha256:4cbf2bf5115ac66ea8eb3fc9b7c74d3327eb3ceba7380ca1947160a3291ebaa7`
- Eligibility: `DEVELOPMENT_ONLY`

## Dataset

- Packages: `8`
- Symbols: `RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, SBIN, ITC, LT`

- `RELIANCE`: id=`zerodha_nse_daily_reliance_20180101_20260812` ver=`v1` bars=`2134` range=`2018-01-01`→`2026-08-12` hash=`sha256:a105b866e61c5ae653479c55ec06710f781c9ca3bc9bf8a1633ef4639373b0f3` price_policy=`unknown`
- `TCS`: id=`zerodha_nse_daily_tcs_20180101_20260812` ver=`v1` bars=`2133` range=`2018-01-01`→`2026-08-12` hash=`sha256:c9f39e0633c6be73124cfe5fb8e744619c466192a161d28298adf796c4ae4813` price_policy=`unknown`
- `INFY`: id=`zerodha_nse_daily_infy_20180101_20260812` ver=`v1` bars=`2133` range=`2018-01-01`→`2026-08-12` hash=`sha256:8f4db38d8ff24e58b84cc91933da1ff4c046f70f73321be21cdd93208764c372` price_policy=`unknown`
- `HDFCBANK`: id=`zerodha_nse_daily_hdfcbank_20180101_20260812` ver=`v1` bars=`2133` range=`2018-01-01`→`2026-08-12` hash=`sha256:d4580e02206a7e3339ed31898cecf3b727fc9e98ed157c0ff49c0da5c1234e61` price_policy=`unknown`
- `ICICIBANK`: id=`zerodha_nse_daily_icicibank_20180101_20260812` ver=`v1` bars=`2133` range=`2018-01-01`→`2026-08-12` hash=`sha256:e4869ad595025041d947bb728fa0afc40cca4be8d1e95d4c0ee976644683554e` price_policy=`unknown`
- `SBIN`: id=`zerodha_nse_daily_sbin_20180101_20260812` ver=`v1` bars=`2133` range=`2018-01-01`→`2026-08-12` hash=`sha256:a46f6aef48f187e921858e9a688540f25095e2e1c08ec7bedfff34415848ebf5` price_policy=`unknown`
- `ITC`: id=`zerodha_nse_daily_itc_20180101_20260812` ver=`v1` bars=`2133` range=`2018-01-01`→`2026-08-12` hash=`sha256:ba411d2f8cf5b73a0d8497fe8b21c9901d2155df3a3c0e5be71e769d8fab1757` price_policy=`unknown`
- `LT`: id=`zerodha_nse_daily_lt_20180101_20260812` ver=`v1` bars=`2133` range=`2018-01-01`→`2026-08-12` hash=`sha256:7ef6e626f11bc7bc65681f9537dd6dc25f690ef109104f272ee250f9ad2fdc8f` price_policy=`unknown`

## Corporate actions

- File: `/Users/sakshambansal/Desktop/Desktop 21-07-2026/Quant-fund/CF-CA-equities-01-01-2009-to-01-08-2026.csv`
- File hash: `sha256:825c04297f4b943ddc0e5761d57473f680afae249bba956e60cbb0ea2e746782`

| symbol | events | known | unknown | coverage | blockers |
|---|---:|---:|---:|---|---|
| RELIANCE | 23 | 2 | 21 | PARTIAL | unknown_or_other_ca_types_present;no_split_bonus_events_in_window_or_file |
| TCS | 77 | 0 | 77 | PARTIAL | unknown_or_other_ca_types_present;no_split_bonus_events_in_window_or_file |
| INFY | 40 | 0 | 40 | PARTIAL | unknown_or_other_ca_types_present;no_split_bonus_events_in_window_or_file |
| HDFCBANK | 22 | 0 | 22 | PARTIAL | unknown_or_other_ca_types_present;no_split_bonus_events_in_window_or_file |
| ICICIBANK | 17 | 0 | 17 | PARTIAL | unknown_or_other_ca_types_present;no_split_bonus_events_in_window_or_file |
| SBIN | 19 | 0 | 19 | PARTIAL | unknown_or_other_ca_types_present;no_split_bonus_events_in_window_or_file |
| ITC | 27 | 1 | 26 | PARTIAL | unknown_or_other_ca_types_present;no_split_bonus_events_in_window_or_file |
| LT | 25 | 0 | 25 | PARTIAL | unknown_or_other_ca_types_present;no_split_bonus_events_in_window_or_file |

## Quality / calendar

- `RELIANCE`: errors=`1743` warnings=`0` blocked=`False` missing_sessions=`176` coverage=`0.763122`
- `TCS`: errors=`1742` warnings=`0` blocked=`False` missing_sessions=`176` coverage=`0.763122`
- `INFY`: errors=`1742` warnings=`0` blocked=`False` missing_sessions=`176` coverage=`0.763122`
- `HDFCBANK`: errors=`1742` warnings=`0` blocked=`False` missing_sessions=`176` coverage=`0.763122`
- `ICICIBANK`: errors=`1742` warnings=`0` blocked=`False` missing_sessions=`176` coverage=`0.763122`
- `SBIN`: errors=`1742` warnings=`0` blocked=`False` missing_sessions=`176` coverage=`0.763122`
- `ITC`: errors=`1742` warnings=`0` blocked=`False` missing_sessions=`176` coverage=`0.763122`
- `LT`: errors=`1742` warnings=`0` blocked=`False` missing_sessions=`176` coverage=`0.763122`

## Leaderboard (ranked by VALIDATION score — not TEST)

| Rank | Strategy | Stocks | Mean OOS Return | Sharpe | Max DD | Trades | DSR | Robust | Accepted |
|---:|---|---:|---:|---:|---:|---:|---:|---|---:|
| 1 | buy_and_hold | 8 | 0.39447462596469274 | 0.8443980431465217 | -0.15271918263758094 | 8 | 0.9991668383642466 | True | 0 |
| 2 | mean_reversion | 8 | -0.004124187227680209 | 0.13798620951153903 | -0.2076239421114917 | 467 | 0.507491963731884 | False | 0 |
| 3 | ma_cross | 8 | 0.3226421289126683 | 0.2429819216570548 | -0.3014051737445805 | 650 | 0.5033280412088187 | False | 0 |
| 4 | momentum | 8 | 0.30452479031066815 | 0.14924990907555624 | -0.3161878700505417 | 936 | 0.375 | False | 0 |
| 5 | vol_breakout | 8 | -0.09872794247503758 | -0.6462422942403658 | -0.2888480611090977 | 1759 | 0.12500000000000017 | False | 0 |

## Walk-forward / Robustness / Leakage / Reproducibility

- Walk-forward: `PASS`
- Robustness: `PASS`
- Leakage: `PASS`
- Future CA leakage: `None`
- Next-bar-open: `None`
- Reproducibility: `PASS`
- Regime: `None`
- Trial count: `225`

## Acceptance

- Accepted count: `0`
- Rejected count: `40`

## PAPER_CANDIDATE

- `{"PAPER_CANDIDATE": false, "reason": "no_strategy_passed_existing_acceptance_gates", "note": "DEVELOPMENT_ONLY datasets cannot be research-accepted"}`

## Safety

- orders_submitted: `0`
- place_order_called: `0`
- broker_write_capability: `DISABLED`
- live_trading: `DISABLED`
- kill_switch: `ARMED`

## Blockers

- DEVELOPMENT_ONLY / non_exchange Zerodha provenance
- Existing score_policy_v1 rejects development_only datasets
- Calendar/PIT/universe completeness still required for RESEARCH_ELIGIBLE
- No Zerodha eligibility shortcut

> Historical strategy validation only. No broker order submission occurred.

