# PIT Historical Universe Layer

The point-in-time (PIT) universe layer answers one research question:

> **Which instruments were in the universe on date `D`?**

It lives in `src/quantfund/research/universe/` and sits on top of the existing
`quantfund.data.universe` membership primitives. It resolves **membership +
identity only** — it never reads or adjusts execution prices — so corporate
actions stay strictly separate from RAW prices. It never enables paper or live
trading.

## Design guarantees

1. **Point-in-time membership.** Membership is resolved from dated interval
   evidence (`member_from` / `member_to`), never from today's constituent list.
   A `current_snapshot_only` universe queried off its `as_of_date` returns
   `UNKNOWN`, and applying a snapshot across a historical range is flagged
   (`current_snapshot_used_as_history`).
2. **No today-universe-for-history.** See guarantee 1 — historical dates never
   inherit the current roster.
3. **Survivorship-safe.** A security that was a member on `D` and later delisted
   is still returned as a member on `D`. Delisting never erases history
   (`PITMember.delisted` / `delisting_date` are surfaced, not filtered out).
4. **Pre-membership prevention.** A security cannot appear in the universe
   before its `member_from` date. Inside a `full_pit` coverage window this is a
   known `FALSE`; before the coverage window it is `UNKNOWN`.
5. **Stable instrument identity.** Identity is bound to `exchange:ISIN` when an
   authoritative ISIN exists (`IdentityGrade.AUTHORITATIVE_ISIN`). A broker
   token / `exchange:SYMBOL` id with no ISIN is `BROKER_RESOLVED` (weak); no
   stable id at all is `UNKNOWN`. A ticker is never treated as identity.
6. **ISIN mapping only where authoritative.** ISIN is read from instrument
   metadata; a null ISIN stays null. No ISIN is ever fabricated.
7. **Corporate actions separate from RAW prices.** This layer touches only
   membership + identity and never opens a price series, so it structurally
   cannot blend adjusted and raw prices.
8. **Missing information is `UNKNOWN`, never fabricated.** `MembershipAnswer`
   keeps `UNKNOWN` distinct from `FALSE`; missing evidence keeps research
   eligibility `False`.

## Module map

| File | Responsibility |
| --- | --- |
| `identity.py` | `bind_identity()` → `IdentityBinding` with `AUTHORITATIVE_ISIN` / `BROKER_RESOLVED` / `UNKNOWN` grade; `instrument_identity_coverage()`. |
| `pit.py` | `resolve_pit_universe(universe, as_of, instruments)` → `PITUniverseSnapshot` with `members` (TRUE), `unknown`, and `excluded` (FALSE) kept separate. |
| `coverage.py` | `evaluate_research_universe_coverage(...)` → the mandated coverage metrics and a fail-closed `research_eligibility` verdict. |
| `report.py` | `build_pit_universe_report(...)` inspects the real repository state honestly and writes the coverage artifacts. |

## Coverage metrics and eligibility

`evaluate_research_universe_coverage` reports:

- `membership_coverage_ratio` — known (TRUE/FALSE) ÷ total membership queries.
- `instrument_identity_coverage` — fraction with authoritative `exchange:ISIN`.
- `delisted_coverage` — measurable terminal-event coverage level.
- `unknown_membership_count` — session×instrument answers that are `UNKNOWN`.
- `research_eligibility` — universe-layer readiness (fails closed).

The eligibility verdict is a **universe-layer** readiness gate. It never enables
trading and does not override the central dataset certification gate; it only
reports whether the PIT universe itself is research-grade. Fail-closed
thresholds (documented policy, not toggles):

- `membership_coverage_ratio == 1.0` and `unknown_membership_count == 0`.
- Universe completeness in `{partial_pit, full_pit}` (not `current_snapshot_only`).
- `instrument_identity_coverage == 1.0` (authoritative ISIN for every member).
- `delisted_coverage` in `{partial, complete}`.

Any unmet condition adds a blocker and keeps `research_eligibility = false`.

## Activating full scoring

Drop a certified membership ledger at:

```
data/research/universe/<universe_id>/membership.(json|csv)
```

CSV columns: `instrument_id, symbol, member_from, source` (optional
`member_to`, `verification_status`, `evidence_reference`). The ledger is
audited for duplicate/overlapping intervals before scoring
(`build_universe_from_membership_file`). Until such a ledger exists, the runner
reports every historical session as `UNKNOWN` and fails closed.

## How to run

```bash
make pit-universe-coverage
# or
.venv/bin/python scripts/run_pit_universe_coverage.py
```

Outputs `reports/pit_universe_coverage.json` (and a `.md` companion).

## Current repository verdict

As of the latest run there is **no authoritative PIT membership ledger** and the
broker packages carry a **null ISIN**, so:

| Metric | Value |
| --- | --- |
| `membership_coverage_ratio` | `0.0` |
| `instrument_identity_coverage` | `0.0` |
| `delisted_coverage` | `none` |
| `unknown_membership_count` | `17064` (8 instruments × 2133 sessions) |
| `research_eligibility` | `false` |

**STOP: coverage is insufficient for research.** The layer is built, tested, and
fails closed. To become research-grade it requires (a) an authoritative dated
index-membership ledger and (b) authoritative `exchange:ISIN` identity plus a
terminal-event ledger for delisted coverage. None of these can be invented.
