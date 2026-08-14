# Research Data Certification

This document reports the certification of the **current repository research-data
state** produced by the new data-acquisition / certification layer, and STOPS.
No eligibility, safety, DSR, PIT, leakage, reproducibility, or broker-write gate
was modified, and no data was fabricated.

Regenerate with:

```bash
make certify-research-data
# or
.venv/bin/python scripts/run_research_data_certification.py
```

## Layer overview

| Step | Module | Purpose |
|---|---|---|
| Contract | `src/quantfund/research/data_contract/` | Versioned `ResearchDatasetPackage` with per-record `SourceProvenance` |
| Providers | `src/quantfund/research/providers/` | `ResearchDataProvider` interface + fail-closed adapters (Zerodha stays `non_exchange`) |
| Ingestion | `src/quantfund/research/ingestion/` | Deterministic ingest, content hashes, dup/missing/closed-session detection, normalization — never repairs gaps |
| Certification | `src/quantfund/research/certification/` | Six per-dimension certs + aggregator that runs the **unmodified** `ResearchEligibilityChecker` |
| Immutability | `src/quantfund/research/certification/immutability.py` | Writes `manifest/package/provenance/checksums/certification.json`; refuses overwrite |

The aggregator (`certify_dataset`) never re-implements eligibility logic: it
builds `DatasetCertificationFacts` and evaluates them through
`quantfund.data.eligibility.ResearchEligibilityChecker`. It only ever *tightens*
by additionally failing closed on any sub-certification, non-reproducibility,
non-immutability, or leakage.

## Current certification result

| Field | Value |
|---|---|
| `source_grade` | `non_exchange` |
| `data_class` | `DEVELOPMENT_DATA` |
| `capability_source_bar_ok` | `false` |
| `membership_coverage_ratio` | `0.0` |
| `instrument_identity_coverage` | `0.0` |
| `delisted_coverage` | `unknown` |
| `corporate_action_coverage` | `none` |
| `calendar_errors` | `0` (no bars ingested; calendar not authoritative → `calendar_verified=false`) |
| `research_eligible` | **`false`** |
| `verdict` | **`DEVELOPMENT_ONLY`** |

### Why (capability gaps — no authoritative source configured)

- **OHLCV**: only Zerodha (broker-redistributed, `non_exchange`) is available; it is not exposed as research-grade.
- **Security master**: no authoritative symbol ↔ ISIN ↔ instrument_id ledger.
- **PIT membership**: no dated membership ledger; refuses to backfill from today's roster.
- **Delistings**: no terminal-event ledger.
- **Calendar**: no authoritative NSE session/holiday reference for certification.
- **Corporate actions**: no verified CA ledger.

These match the independent authoritative cross-checks:
Phase 18 `research_eligible = false`, `accepted_strategies = not_run`; PIT
`completeness = none`, `membership_coverage_ratio = 0.0`.

## Safety state (unchanged)

| Invariant | Value |
|---|---|
| `orders_submitted` | `0` |
| `place_order_called` | `0` |
| `live_trading` | `DISABLED` |
| `broker_write_capability` | `DISABLED` |
| `kill_switch` | `ARMED` |
| `auto_graduate_to_live` | `false` |

## Decision

`research_eligible == false` → **Phase 19 strategy search was NOT run** (fail-closed
STOP). The success condition (research-grade source + `membership_coverage_ratio = 1.0`
+ `instrument_identity_coverage = 1.0` + complete delisted coverage +
`calendar_errors = 0` + immutable/reproducible dataset) is **not met**.

To unblock, supply a genuinely research-grade, licensed/exchange-authoritative
source with full provenance (OHLCV + PIT membership + security master + terminal
events + calendar + corporate actions) and re-run certification. The
infrastructure will certify it end-to-end and only then return
`RESEARCH_ELIGIBLE`. Until then the system remains development-only by design.
