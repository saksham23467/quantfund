# Data license assumptions (Phase 3.5 / Phase 5 / Phase 7)

QuantFund separates **code**, **synthetic fixtures**, and **third-party market data**.

## License record template (external research packages)

When ingesting a licensed package, record in `package.json` and preferably `LICENSE.json`:

| Field | Example |
|-------|---------|
| `license_status` | `verified` / `internal_research_only` / `redistributable` / `unknown` / `prohibited` / `expired` |
| `license_reference` | Contract / product SKU |
| `legal_source` | Exchange / redistributor legal entity |
| `research_use_allowed` | `true` only with contractual evidence |
| `redistribution_allowed` | `false` unless explicitly permitted |
| `acquisition_method` / `acquisition_timestamp` | How/when the package was obtained |
| `capabilities.authority_evidence_refs` | Contract IDs / product docs (not auto-trust) |

Do **not** set `research_eligible` in the package — eligibility is derived.

Research eligibility **rejects** `unknown`, `prohibited`, and `expired` unless an existing policy explicitly permits otherwise.

Set `QUANTFUND_RESEARCH_PACKAGE` to the local package root. Credentials must not be hardcoded.

## Synthetic fixtures

Paths such as:

- `tests/fixtures/phase35/pilot_package/`
- `tests/fixtures/phase5/`
- `tests/fixtures/synthetic_bars.csv`

are **fabricated** for continuous integration and pipeline verification.

- License: same as the repository code (usable in tests).
- They must **never** be labeled `source_grade=exchange` or `research_eligible`.
- ISINs/symbols may mirror real securities for identity tests; **prices are not real**.

## Yahoo Finance (`yfinance`)

- `source_grade = non_exchange` always.
- Cannot become `research_eligible` merely because bars validate.
- Phase 12 may use yfinance as a **development / controlled paper simulation** market-data
  source only. Paper results on yfinance are **not** research evidence and **not**
  live-execution quality evidence.
- Yahoo Terms of Service apply to any downloaded content.
- Do **not** commit bulk Yahoo RAW downloads to the public repository if redistribution is prohibited.
- Local RAW downloads under `data/raw/yfinance/` are intended to stay local / gitignored.

## User-supplied historical corporate actions (CF-CA equities)

Local files such as `CF-CA-equities-01-01-2009-to-01-08-2026.csv` ingested via
`quantfund.data.corporate_actions.historical_local`:

- Are **user-supplied / local** development inputs.
- Source provenance is recorded (filename, SHA-256, row count, coverage dates).
- **Redistribution rights are unknown** unless explicitly established by the user.
- `source_grade = non_exchange`, `exchange_authority = false`.
- **Do not** claim NSE authorization or exchange-grade research status merely because
  the file contains historical corporate-action rows.
- Development / exploratory use only until licensing and authority are proven.
- Must not be used to force `research_eligible` or `full_verified` CA coverage.
- Prefer keeping bulk RAW copies under `data/raw/historical_local_ca/` (gitignored).

## NSE / NSE Indices Limited materials

- Holiday calendars under `data/calendars/nse_eq/` are curated from **public NSE circulars**
  with source references in each version’s `SOURCES.md`.
- NIFTY50 PIT file `pit_partial_documented_v1` records **only** reconstitution events
  documented via NSE Indices Ltd. communications / SEBI-mandated AMC disclosures.
  It is **not** a full constituent archive and must not be redistributed as if it were
  an official complete historical product.
- Full historical Market Cap / Weightage archives should be obtained from
  https://www.niftyindices.com/reports/historical-data under NSE Indices terms.
  Import into a **new** `universe_version`; never overwrite existing versions.

## Paid / exchange redistributors

When a licensed research vendor is configured:

1. Record license terms in the package `licensing_notes` and this file.
2. Set `source_grade` and `exchange_authority` **explicitly** in package metadata.
3. Keep proprietary RAW payloads out of git unless the license permits redistribution.
4. Prefer the `LocalResearchPackageProvider` adapter so vendor SDKs stay out of the
   research engine.

## Non-negotiable

- Do not fabricate missing prices or membership.
- Do not weaken `ResearchEligibilityChecker` to promote a dataset.
- Do not claim research-grade without evidence in provenance + capabilities.
