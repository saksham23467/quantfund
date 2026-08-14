# Phase 7 Data Contract — Research Package Layout

## Directory layout

```
QUANTFUND_RESEARCH_PACKAGE/
    package.json
    LICENSE.json          # recommended
    provenance.json       # recommended
    checksums.sha256      # required for integrity when present
    instruments/          # or instruments.json
    bars/
    corporate_actions/    # or corporate_actions.json
    universe/
    calendars/
    delisted/             # or terminal_events.json
```

## `package.json` required identity fields

| Field | Notes |
|-------|-------|
| `package_id` | Stable package identity |
| `package_version` | Semver or vendor version |
| `provider` | Legal / vendor name |
| `source_grade` | `exchange` \| `paid` \| `non_exchange` \| `synthetic` |
| `exchange_authority` | Boolean claim; must be evidenced |
| `license_status` | See license vocabulary |
| `acquisition_timestamp` | ISO-8601 |
| `coverage_start` / `coverage_end` | Declared window |
| `frequencies` | e.g. `["1d"]` |
| `exchanges` | e.g. `["NSE"]` |
| `asset_classes` | e.g. `["equity"]` |
| `checksum_algorithm` | `sha256` |
| `schema_version` | `quantfund_research_package_v1` |

Authority is **never** inferred from filenames.

## Forbidden package fields

Packages must **not** declare:

- `research_eligible`
- `research_eligibility`
- `eligibility`
- `accepted`

Eligibility is derived by `ResearchEligibilityChecker`.

## License vocabulary

| Status | Research path |
|--------|---------------|
| `verified` | Allowed if other gates pass |
| `internal_research_only` | Allowed if other gates pass |
| `redistributable` | Allowed if other gates pass |
| `unknown` | Rejected for research |
| `prohibited` | Package ingest / research rejected |
| `expired` | Package ingest / research rejected |

## Capability declarations

Providers must declare capabilities explicitly (e.g. `supports_daily_bars`, `supports_pit_universe`, `supports_delisted_instruments`, `supports_licensing_evidence`). Claiming a capability without payload evidence yields warnings/errors. Interfaces alone are not evidence.

## Instrument identity

Each instrument should carry:

- stable `instrument_id`
- ISIN, exchange, symbol
- `symbol_history` / historical symbols
- `listing_date` / `delisting_date`
- `status`
- provider mappings
- `terminal_event_id` when applicable

Identity must not depend on today's Yahoo ticker.

## NIFTY50 PIT membership CSV

Required columns: `instrument_id`, `symbol`, `member_from`, `source`  
Optional: `member_to`, `verification_status`, `evidence_reference`

Rules:

- no silent interpolation
- no invented membership
- unknown remains UNKNOWN
- overlaps / duplicates fail import
- gaps are reported
- effective dates deterministic

## Corporate actions

Supported verified record types: split, bonus, dividend, symbol change, merger, demerger, rights.

No naive automatic merger/demerger price reconstruction. RAW OHLC remains immutable.
