# PHASE 18 — Research Dataset Eligibility

Phase 18 research-dataset eligibility gate only. NO STRATEGY SEARCH, NO PAPER TRADING, NO LIVE TRADING.

## Final gate status

- `research_eligible = false`
- `paper_candidate = false`
- `live_enabled = false`
- `orders_submitted = 0`
- `place_order_called = 0`
- Eligibility aggregate: `DEVELOPMENT_ONLY`
- Any research-eligible: `False`
- Zerodha shortcut: `False`
- Stopped at blocker: `exchange_grade_source_certification`

## Ordered blocker resolution

| # | Blocker | Status | Fail-closed reason (summary) |
|---|---|---|---|
| 1 | `exchange_grade_source_certification` | **UNRESOLVED** | Zerodha Kite historical is broker-redistributed data, not exchange-authoritative. |
| 2 | `calendar_residuals` | **UNRESOLVED** | Residual sessions (bar_on_closed_session / missing_open_session) reflect genuine calendar-vs-data mismatches. |
| 3 | `corporate_action_completeness` | **RESOLVED** | Research-bar CA coverage (splits_bonus_dividends) is derived only from CA events actually present; dividends/bonus/splits are not invented. |
| 4 | `pit_universe_membership_ledger` | **UNRESOLVED** | No point-in-time universe membership ledger exists in any package. |
| 5 | `instrument_identity_isin` | **UNRESOLVED** | instrument_token is genuinely present (broker-resolved) and is now read correctly, removing a false 'missing_instrument_token'. |
| 6 | `delisted_security_coverage` | **UNRESOLVED** | No delisting / terminal-event ledger exists for the universe. |
| 7 | `capability_source_bar_ok` | **UNRESOLVED** | Derived from source grade: a non_exchange provider cannot satisfy the research source bar. |

## Blocker detail

### `exchange_grade_source_certification` — UNRESOLVED

- Current implementation: src/quantfund/data/providers/zerodha_historical.py:104-108 (source_grade=NON_EXCHANGE); src/quantfund/phase17c/certify_gate.py:38-63 (source_grade='non_exchange', data_class='DEVELOPMENT_DATA', never forged); gate in src/quantfund/data/eligibility.py:73-76,60-65
- Evidence: `{"data_class": "DEVELOPMENT_DATA", "license_status": "broker_account_restricted", "source_grade": "non_exchange"}`
- Fail-closed reason: Zerodha Kite historical is broker-redistributed data, not exchange-authoritative. Marking it exchange/paid grade would forge source authority, which is explicitly forbidden. No exchange-authority attestation exists in any package.
- Required genuine artifact: A market-data license/feed from an exchange-authoritative or paid research-grade vendor (e.g. official NSE EOD/tick or equivalent) with verifiable provenance. Cannot be synthesized.

### `calendar_residuals` — UNRESOLVED

- Current implementation: src/quantfund/data/calendar/nse.py (verified NSE calendar); src/quantfund/phase17a/quality.py:run_symbol_quality (bar_on_closed_session / missing_open_session ERRORs); gate in src/quantfund/data/eligibility.py:104-107
- Evidence: `{"aggregate_quality_error_count": 111}`
- Fail-closed reason: Residual sessions (bar_on_closed_session / missing_open_session) reflect genuine calendar-vs-data mismatches. Resolving them by inserting or deleting bars would be silent data repair (forbidden), and correcting the certified calendar requires an authoritative NSE session/holiday source.
- Required genuine artifact: An authoritative NSE trading-session/holiday reference for the specific residual dates so the certified calendar can be reconciled against authority (never by mutating bars).

### `corporate_action_completeness` — RESOLVED

- Current implementation: src/quantfund/phase17a/ca.py:analyze_ca_for_symbol; src/quantfund/data/corporate_actions/coverage.py:71-119; label mapping in src/quantfund/phase17c/pipeline.py:52-58; gate in src/quantfund/data/eligibility.py:98-103
- Evidence: `{"coverage_labels": ["PARTIAL"]}`
- Fail-closed reason: Research-bar CA coverage (splits_bonus_dividends) is derived only from CA events actually present; dividends/bonus/splits are not invented. Production still requires full_verified (stricter).
- Required genuine artifact: For production candidacy: a fully verified corporate-action ledger (full_verified). Research bar is satisfied when genuine split/bonus/dividend events are present.

### `pit_universe_membership_ledger` — UNRESOLVED

- Current implementation: src/quantfund/phase17c/identity_pit.py:audit_universe_membership (fails closed: no ledger => every session UNKNOWN, never TRUE); gate in src/quantfund/data/eligibility.py:87-132
- Evidence: `{"aggregate_unknown_membership_sessions": 17065, "membership_ledger_present": false}`
- Fail-closed reason: No point-in-time universe membership ledger exists in any package. Membership is reported UNKNOWN (not invented as TRUE). Today's snapshot must not stand in for history.
- Required genuine artifact: A point-in-time universe membership ledger: constituent membership intervals with verified flags for the traded universe. Absent; cannot be invented.

### `instrument_identity_isin` — UNRESOLVED

- Current implementation: src/quantfund/phase17c/identity_pit.py:audit_instrument_identity (now reads nested 'resolved' fields; instrument_token surfaced, ISIN value-checked and fails closed when null); gate in src/quantfund/data/eligibility.py:142-145
- Evidence: `{"aggregate_identity_issue_count": 8, "instrument_token_present": true, "isin_present": false}`
- Fail-closed reason: instrument_token is genuinely present (broker-resolved) and is now read correctly, removing a false 'missing_instrument_token'. ISIN is genuinely null and is not invented, so 'no_isin_stable_identity' correctly remains.
- Required genuine artifact: Authoritative ISIN mapping (exchange:ISIN) per instrument from a trusted security master. Absent; cannot be invented.

### `delisted_security_coverage` — UNRESOLVED

- Current implementation: src/quantfund/phase17c/certify_gate.py:51 (delisted_coverage='unknown', honest); measurement in src/quantfund/data/instruments/coverage.py:42-127; gate in src/quantfund/data/eligibility.py:134-140
- Evidence: `{"delisted_coverage": "unknown"}`
- Fail-closed reason: No delisting / terminal-event ledger exists for the universe. Coverage is reported 'unknown' (not upgraded to partial/complete without evidence).
- Required genuine artifact: A delisting / terminal-event ledger (delisting dates, survivor mapping) covering the universe. Absent; cannot be invented.

### `capability_source_bar_ok` — UNRESOLVED

- Current implementation: src/quantfund/data/providers/capabilities.py:61-71 (can_satisfy_research_eligibility_source_bar); src/quantfund/phase17c/certify_gate.py:60 (False); gate in src/quantfund/data/eligibility.py:77-84
- Evidence: `{"capability_source_bar_ok": false}`
- Fail-closed reason: Derived from source grade: a non_exchange provider cannot satisfy the research source bar. Resolves automatically once an exchange/paid-grade source (#1) is certified.
- Required genuine artifact: Same as exchange-grade source certification (#1).

## Per-symbol summary

| Symbol | Bars | Identity issues | Unknown membership | Quality errors | Level |
|---|---:|---:|---:|---:|---|
| RELIANCE | 2134 | 1 | 2134 | 13 | development_only |
| TCS | 2133 | 1 | 2133 | 14 | development_only |
| INFY | 2133 | 1 | 2133 | 14 | development_only |
| HDFCBANK | 2133 | 1 | 2133 | 14 | development_only |
| ICICIBANK | 2133 | 1 | 2133 | 14 | development_only |
| SBIN | 2133 | 1 | 2133 | 14 | development_only |
| ITC | 2133 | 1 | 2133 | 14 | development_only |
| LT | 2133 | 1 | 2133 | 14 | development_only |

## Immutability

Eligibility evaluated read-only (write_package=False). No dataset version was created or overwritten.

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

**NO STRATEGY SEARCH, NO PAPER TRADING, AND NO LIVE TRADING WAS STARTED.**
