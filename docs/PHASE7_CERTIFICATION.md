# Phase 7 Certification — Evidence Required for RESEARCH_ELIGIBLE

Certification produces a reproducible `DatasetCertification`:

- `dataset_id` / `dataset_version`
- `certified_at`
- `facts_hash`
- `eligibility`
- `blockers[]` / `warnings[]`
- `metrics` (membership, delisted, CA, quality, hashes)
- `provenance` / `license`
- `quality_summary`

Boolean fields in `package.json` are **not trusted**. Eligibility is derived from `DatasetCertificationFacts`.

## Eligibility hierarchy (unchanged)

1. `DEVELOPMENT_ONLY`
2. `RESEARCH_ELIGIBLE`
3. `PRODUCTION_CANDIDATE`

## Evidence required for RESEARCH_ELIGIBLE

All of the following must hold under the current policy:

| Gate | Requirement |
|------|-------------|
| Source grade | `exchange` or `paid` (not `synthetic` / `non_exchange`) |
| Capability source bar | Provider attestation can satisfy research source bar |
| Exchange authority | Claim consistent with provenance; not forged |
| License | Not `unknown` / `prohibited` / `expired` |
| Provenance | Complete (provider, timestamps, hashes, license) |
| Calendar | Verified NSE (or policy-accepted) calendar |
| Universe | `partial_pit` or `full_pit` (not `current_snapshot_only`) |
| Membership | `membership_coverage_ratio` ≥ policy minimum (default 1.0) |
| UNKNOWN sessions | `unknown_membership_session_count == 0` for research |
| full_pit claim | Forbidden while unknown sessions remain |
| Corporate actions | Coverage in policy set (e.g. splits/bonus/dividends) |
| Delisted coverage | At least `partial` for research; `complete` for production |
| Quality | Zero mandatory ERRORs |
| Integrity | Package checksums / content hash consistent |
| Synthetic flag | `synthetic=true` always blocks research |

## Production candidate (stricter)

Additionally requires full PIT, full verified CA, and complete delisted coverage (per policy).

## What Phase 7 does **not** promise

- That a licensed package is present in this environment
- That strategies will be profitable
- That synthetic / yfinance data can become research-eligible
- That broker APIs are an automatic research source

If the package is insufficient, **`DEVELOPMENT_ONLY` is the correct answer.**
