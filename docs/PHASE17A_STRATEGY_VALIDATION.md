# PHASE 17A — Real Zerodha Strategy Validation

## Prominence

Historical strategy validation only. No broker order submission occurred.

- Result: `PASS`
- Provider: `ZERODHA`
- Data: `REAL HISTORICAL DATA`
- Combined dataset hash: `sha256:bfe210177e538b100fd0477b3e7755122ef3cac19be456d39fd6c5de08dd14a5`
- Eligibility: `DEVELOPMENT_ONLY`

## Dataset

- Packages: `8`
- Symbols: `RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, SBIN, ITC, LT`

- `RELIANCE`: id=`zerodha_nse_daily_reliance_20240101_20240628` ver=`v2` bars=`123` range=`2024-01-01`→`2024-06-28` hash=`sha256:5012dac0bfae34bcc8ddaae48f8264037233c3ca17f18a1130e59fd7ff9a532f` price_policy=`unknown`
- `TCS`: id=`zerodha_nse_daily_tcs_20240101_20240628` ver=`v2` bars=`123` range=`2024-01-01`→`2024-06-28` hash=`sha256:30b130ac452651dcc34083872c53771fc39c345bfc5b7b6a388b60209cf3fb34` price_policy=`unknown`
- `INFY`: id=`zerodha_nse_daily_infy_20240101_20240628` ver=`v2` bars=`123` range=`2024-01-01`→`2024-06-28` hash=`sha256:5391deab185fb6c576660b51513e1ac30d47f06b4cb6741a8c7b6ad5e267a09e` price_policy=`unknown`
- `HDFCBANK`: id=`zerodha_nse_daily_hdfcbank_20240101_20240628` ver=`v2` bars=`123` range=`2024-01-01`→`2024-06-28` hash=`sha256:11ad54fa2d2a00de95c41ea9dadb81bfc82f1c5659e9c8cd0a7a6c6e246432cd` price_policy=`unknown`
- `ICICIBANK`: id=`zerodha_nse_daily_icicibank_20240101_20240628` ver=`v2` bars=`123` range=`2024-01-01`→`2024-06-28` hash=`sha256:e8ca7ac7f9743ebc64842a26cf73eeda04a98749da49afc2bed808ad668104a1` price_policy=`unknown`
- `SBIN`: id=`zerodha_nse_daily_sbin_20240101_20240628` ver=`v2` bars=`123` range=`2024-01-01`→`2024-06-28` hash=`sha256:ba1271a2ef33772dd43bdf8df025f6e8b81ac1a8723ebb7dd962368f978e68ce` price_policy=`unknown`
- `ITC`: id=`zerodha_nse_daily_itc_20240101_20240628` ver=`v2` bars=`123` range=`2024-01-01`→`2024-06-28` hash=`sha256:94fa51aff703ddd7255f6aa087e292bd33e1df7faa5954eec55f0c96adfe6ead` price_policy=`unknown`
- `LT`: id=`zerodha_nse_daily_lt_20240101_20240628` ver=`v2` bars=`123` range=`2024-01-01`→`2024-06-28` hash=`sha256:7695b5a4b68ec5a52eba29b31e037284ad16976d2eae8738770e1f5a43e4a832` price_policy=`unknown`

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

- `RELIANCE`: errors=`52` warnings=`0` blocked=`False` missing_sessions=`25` coverage=`0.793388`
- `TCS`: errors=`52` warnings=`0` blocked=`False` missing_sessions=`25` coverage=`0.793388`
- `INFY`: errors=`52` warnings=`0` blocked=`False` missing_sessions=`25` coverage=`0.793388`
- `HDFCBANK`: errors=`52` warnings=`0` blocked=`False` missing_sessions=`25` coverage=`0.793388`
- `ICICIBANK`: errors=`52` warnings=`0` blocked=`False` missing_sessions=`25` coverage=`0.793388`
- `SBIN`: errors=`52` warnings=`0` blocked=`False` missing_sessions=`25` coverage=`0.793388`
- `ITC`: errors=`52` warnings=`0` blocked=`False` missing_sessions=`25` coverage=`0.793388`
- `LT`: errors=`52` warnings=`0` blocked=`False` missing_sessions=`25` coverage=`0.793388`

## Leaderboard (ranked by VALIDATION score — not TEST)

| Rank | Strategy | Stocks | Mean OOS Return | Sharpe | Max DD | Trades | DSR | Robust | Accepted |
|---:|---|---:|---:|---:|---:|---:|---:|---|---:|
| 1 | buy_and_hold | 8 | 0.010222236285269734 | 0.5362629123550955 | -0.037781313756318484 | 8 | 0.6273356123526485 | False | 0 |
| 2 | mean_reversion | 8 | 0.008262896044883977 | 0.7810886011672771 | -0.037385846912949765 | 54 | 0.6245737023726486 | True | 0 |
| 3 | momentum | 8 | -0.02092654307602182 | -1.758644412281543 | -0.06083512495514788 | 90 | 0.3736529581188467 | False | 0 |
| 4 | ma_cross | 8 | -0.02159036712185622 | -1.0861259843421494 | -0.06103434044819964 | 69 | 0.20691548417187486 | False | 0 |
| 5 | vol_breakout | 8 | -0.03630891098930111 | -3.6023603881077686 | -0.04370286584448774 | 104 | 1.991821985125597e-11 | True | 0 |

## Walk-forward / Robustness / Leakage / Reproducibility

- Walk-forward: `PASS`
- Robustness: `PASS`
- Leakage: `PASS`
- Future CA leakage: `PASS`
- Next-bar-open: `PASS`
- Reproducibility: `PASS`
- Regime: `REGIME_ANALYSIS_NOT_AVAILABLE`
- Trial count: `80`

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

