# Research Data Gap Inventory (STEP 1 — Audit)

Read-only audit. **No code was modified in this step.** The single remaining
bottleneck is **research eligibility**, which is blocked by the absence of a
genuinely research-grade, licensed, exchange-authoritative data source and its
provenance. None of the missing facts may be fabricated.

## Authoritative gate (must NOT be modified)

- `ResearchEligibilityChecker` — `src/quantfund/data/eligibility.py`
- `DatasetCertificationFacts` + policies — `src/quantfund/data/policy.py`
- Facts are evaluated read-only; metrics can never promote eligibility; forged
  `research_eligible` claims in a manifest are explicitly ignored.

Key thresholds (unchanged): `min_membership_coverage_ratio = 1.0`,
`min_universe_completeness ∈ {partial_pit, full_pit}`,
`min_delisted_coverage ∈ {partial, complete}`, `require_capability_source_bar`,
`require_calendar_verified`, `require_provenance_complete`,
`require_license_not_prohibited`, `allow_unknown_membership_periods = false`.

## Current authoritative blockers

| # | Blocker | Current value | Gate location | Fabricatable |
|---|---|---|---|---|
| 1 | `source_grade` | `non_exchange` | `eligibility.py:73-76` | no |
| 2 | `data_class` | `DEVELOPMENT_DATA` | `eligibility.py:60-65` | no |
| 3 | `capability_source_bar_ok` | `false` | `eligibility.py:77-84`, `capabilities.py:61-71` | no |
| 4 | PIT membership ledger | missing | `eligibility.py:87-114`, `research/universe` | no |
| 5 | `membership_coverage_ratio` | `0.0` | `eligibility.py:116-123` | no |
| 6 | delisted/terminal-event ledger | missing (`unknown`) | `eligibility.py:134-140` | no |
| 7 | authoritative ISIN / security master | missing (ISIN null) | `eligibility.py:142-145`, `identity.py` | no |
| 8 | calendar reconciliation residuals | possible | `eligibility.py:85-86,104-107` | no |
| 9 | Phase 19 strategy search | correctly NOT run | `strategy_research/gates.py` | n/a |
| 10 | accepted strategies | `0` | `strategy_research/framework.py` | n/a |
| 11 | paper candidate | `false` | `phase18/dataset_eligibility.py` | n/a |

## Current dataset package schema

`write_zerodha_dataset_package` (`src/quantfund/data/zerodha_hist/package.py`)
writes an immutable version dir containing `bars.parquet`, `manifest.json`,
`provenance.json`, `quality_report.json`, `corporate_actions.json`,
`instrument_metadata.json`. Manifest carries `source_grade=non_exchange`,
`research_eligible=false`, `eligibility=DEVELOPMENT_ONLY`, `content_hash`.
Overwriting an existing version is refused.

`instrument_metadata.json` resolves `instrument_token` but `isin = null`, so no
`exchange:ISIN` stable identity exists.

## Missing fields by domain

- **OHLCV**: ISIN (null in broker packages).
- **Identity**: ISIN, `valid_from`, `valid_to` (no historical security master).
- **PIT universe**: `universe_id`, `universe_version`, `member_from`,
  `member_to` (no membership ledger at all → membership UNKNOWN everywhere).
- **Delisting**: ISIN, `delisting_date`, `terminal_event_type` (no ledger).
- **Calendar**: authoritative reconciliation source for residual dates.
- **Corporate actions**: verified full CA ledger with source provenance.

## Source requirements to unblock (must be genuinely authoritative)

- **A** Exchange-authoritative / licensed historical OHLCV (`SourceGrade.EXCHANGE|PAID`, `exchange_authority=true`, license VERIFIED).
- **B** Dated PIT index-membership intervals per universe, verified.
- **C** Historical security master: symbol ↔ ISIN ↔ instrument_id with validity ranges.
- **D** Delisting / terminal-event ledger with dates + successor mapping.
- **E** Authoritative NSE trading-session/holiday reference.
- **F** Verified corporate-action ledger, traceable to source, separate from RAW prices.

## Files/classes responsible for each gate

- Eligibility evaluation: `src/quantfund/data/eligibility.py:ResearchEligibilityChecker.evaluate`
- Honest Zerodha facts: `src/quantfund/phase17c/certify_gate.py:build_zerodha_cert_facts`
- Per-symbol certification: `src/quantfund/phase17c/pipeline.py:certify_symbol_package`
- Phase 18 aggregate blockers: `src/quantfund/phase18/dataset_eligibility.py`
- PIT coverage: `src/quantfund/research/universe/coverage.py`
- Phase 19 prerequisite: `src/quantfund/research/strategy_research/gates.py:evaluate_prerequisite`
- Provider source bar: `src/quantfund/data/providers/capabilities.py:can_satisfy_research_eligibility_source_bar`

## Conclusion

`research_eligible = false`. The correct solution is to bring in a genuinely
research-grade source with full provenance. This audit changes nothing; the
subsequent steps build the acquisition/certification infrastructure so that such
a source *can* be certified when it exists — and fail closed until it does.
