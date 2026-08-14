# NIFTY 50 universe definitions

Membership files are **versioned** under:

`universe_version=<version>/membership.json` (and optional `membership.csv`)

## Stage A (current snapshot)

`universe_version=stage_a_sample_v1`  
`completeness = current_snapshot_only`

Snapshot of constituents as-of a capture date. **NOT** historical point-in-time.

**Warning:** NOT POINT-IN-TIME. UNSUITABLE FOR FINAL STRATEGY EVALUATION.

## Partial PIT (documented reconstitutions)

`universe_version=pit_partial_documented_v1`  
`completeness = partial_pit`

Event-sourced inclusions/exclusions from public NSE Indices Ltd. reconstitution
communications only. See that version’s `SOURCES.md`.

- Tracked names with verified intervals → TRUE / FALSE
- Untracked names (e.g. RELIANCE without a row) → **UNKNOWN**
- Never use today’s constituents for historical backtests

## Extending

Import archives via `quantfund.data.universe.import_membership` into a **new**
`universe_version`. Never overwrite an existing version.
