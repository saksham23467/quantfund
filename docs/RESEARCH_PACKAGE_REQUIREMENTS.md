# Research Package Requirements

**Phase 10.5 — Readiness audit (specification / shopping list).**  
This document mirrors gates already enforced in code. It does **not** invent a parallel contract and does **not** weaken eligibility.

Run:

```bash
make audit-research-package
# or
QUANTFUND_RESEARCH_PACKAGE=/path/to/package make audit-research-package
```

## Goal

Acquire a licensed, exchange/paid-grade NSE package that can certify as:

```text
RESEARCH_ELIGIBLE
```

Only then can the Phase 10 ladder reach the **data rung** of:

```text
PAPER_ELIGIBLE
```

Paper still also requires strategy acceptance evidence, sealed TEST, robustness, walk-forward, DSR/trials, operator session, etc. Those are **not** vendor data deliverables.

---

## Hard truths (current environment)

| Fact | Status |
|------|--------|
| Synthetic / yfinance | Permanently `DEVELOPMENT_ONLY` |
| Phase35 pilot fixture | Valid package structure; **not** research-eligible |
| `QUANTFUND_RESEARCH_PACKAGE` (default) | Unset |
| Real orders / live trading | Disabled (Phase 9/11) |
| Eligibility gates weakened? | **No** |

---

## Vendor-neutral package layout

Only paths actually consumed by `LocalResearchPackageProvider` / validators:

```text
QUANTFUND_RESEARCH_PACKAGE/
    package.json                 # REQUIRED
    instruments.json             # instrument master (+ symbol_history)
    corporate_actions.json       # CA ledger
    terminal_events.json         # delistings / terminal events
    universe/
        membership.json          # preferred PIT membership (or .csv)
    bars/
        RELIANCE.csv             # or bars/{instrument_id_sanitized}.csv
        ...
    LICENSE.json                 # optional sidecar
    provenance.json              # optional sidecar
    checksums.sha256             # optional; verified if present
```

**PIT membership:** Prefer package-local `universe/membership.json|csv`.  
If absent, certification may fall back to the repository
`pit_partial_documented_v1` store (often produces UNKNOWN) or an unverified
synthetic fallback — neither proves research-grade PIT. **Do not invent
historical membership.** Target: `unknown_membership_session_count=0` and
`membership_coverage_ratio=1.0` for the certified window.

Platform NSE calendar (verified) lives under `data/calendars/nse_eq/` and is used
by certification; packages must align bars to that session calendar.

---

## Machine-readable checklist

Each item: requirement → implementation → evidence → file → rule → severity → demo.

### Source grade / capability bar

| Field | Value |
|-------|-------|
| requirement | `source_grade` ∈ {`exchange`, `paid`}; not synthetic |
| current implementation | `ResearchEligibilityChecker`; `ProviderCapabilities.can_satisfy_research_eligibility_source_bar` |
| required evidence | Honest grade; `exchange_authority=true` **or** paid grade |
| package field/file | `package.json`: `source_grade`, `exchange_authority`, `synthetic` |
| validation rule | synthetic/non_exchange / `capability_source_bar_ok=false` / `extras.synthetic=true` → `DEVELOPMENT_ONLY` |
| blocking severity | **BLOCKING** |
| current demo status | **BLOCKING** (pilot is synthetic) |

### Market data

| Field | Value |
|-------|-------|
| requirement | Daily OHLCV for instruments over coverage window; clean chronology |
| current implementation | `LocalResearchPackageProvider.get_history`; `run_quality_checks` |
| required evidence | Session-dated RAW OHLCV; no fabricated bars |
| package field/file | `bars/{SYMBOL}.csv` (`timestamp`, open/high/low/close/volume) |
| validation rule | Empty bars abort certify; quality ERRORs (`duplicate_bar`, `invalid_ohlc`, `missing_open_session`, …) → block |
| blocking severity | **BLOCKING** |
| current demo status | **PASS** (structure/bars present on pilot) |

Also expected for a production research buy:

- Trading-session alignment with NSE calendar (no bar-on-closed-session ERRORs)
- Sufficient historical range covering TRAIN/VALIDATION/TEST splits
- Symbol-change / historical identifier continuity via `instrument_id`

### Instrument identity

| Field | Value |
|-------|-------|
| requirement | Stable identity; no collisions; listing intervals coherent |
| current implementation | `data/identity.py` + quality identity ERRORs → `instrument_identity_issues` |
| required evidence | Exchange identifiers (e.g. ISIN), symbol history / changes |
| package field/file | `instruments.json` |
| validation rule | `instrument_identity_issues > 0` → `DEVELOPMENT_ONLY` |
| blocking severity | **BLOCKING** |
| current demo status | **PASS** on pilot fixtures |

### NIFTY50 PIT membership

| Field | Value |
|-------|-------|
| requirement | Point-in-time universe (`partial_pit` or `full_pit`) with effective dates |
| current implementation | `UniverseCompleteness`; membership store / `build_pit_universe` |
| required evidence | Historical NIFTY50 additions/removals; reconstructable PIT |
| package field/file | Universe membership intervals (repo `data/universes/...` or equivalent) |
| validation rule | `current_snapshot_only` forbidden; completeness must meet policy min |
| blocking severity | **BLOCKING** |
| current demo status | Partial PIT may load, but see UNKNOWN below |

### UNKNOWN membership

| Field | Value |
|-------|-------|
| requirement | **Zero** UNKNOWN membership sessions for the certified research set |
| current implementation | `compute_membership_coverage` + eligibility |
| required evidence | Membership TRUE/FALSE for every symbol×session traded |
| package field/file | PIT membership covering all package symbols in window |
| validation rule | `unknown_membership_session_count > 0` **or** `membership_coverage_ratio < 1.0` → block |
| blocking severity | **BLOCKING** |
| current demo status | **BLOCKING** on documented partial NIFTY50 + continuous names |

### Corporate actions

| Field | Value |
|-------|-------|
| requirement | Overall coverage ≥ `splits_bonus_dividends` |
| current implementation | `derive_ca_coverage_report` |
| required evidence | Splits, bonuses, dividends with effective dates + provenance |
| package field/file | `corporate_actions.json` |
| validation rule | overall ∉ {`splits_bonus_dividends`, `full_verified`} → block |
| blocking severity | **BLOCKING** |
| current demo status | **PASS** overall on synthetic pilot CA set |

**Mergers / demergers:** schema + `requires_manual_treatment` only.  
Architecture does **not** auto-reconstruct merger prices. Not required for the RESEARCH_ELIGIBLE CA minimum. Rights/issues only if needed to reach the declared coverage level.

### Delisted / terminal events

| Field | Value |
|-------|-------|
| requirement | Delisted coverage ≥ `partial` |
| current implementation | `measure_delisted_coverage` |
| required evidence | Delisting dates and/or terminal DELISTING events; identity mapping |
| package field/file | `instruments.json` (`delisting_date`); `terminal_events.json` |
| validation rule | `none` / `unknown` insufficient for research |
| blocking severity | **BLOCKING** |
| current demo status | **BLOCKING** (`none` on pilot) |

### NSE calendar

| Field | Value |
|-------|-------|
| requirement | Verified NSE equity sessions (holidays, Muhurat/special sessions) |
| current implementation | `NSECalendarProvider` (`calendar_verified=true`) |
| required evidence | Versioned curated calendar with provenance |
| package field/file | Platform `data/calendars/nse_eq/.../calendar.json` (facts record `calendar_id` / `calendar_version`) |
| validation rule | `calendar_verified=false` → block |
| blocking severity | **BLOCKING** |
| current demo status | **PASS** (platform calendar verified) |

Unverified XBOM proxy calendars force development-only datasets.

### Provenance

| Field | Value |
|-------|-------|
| requirement | Complete research provenance |
| current implementation | `ProvenanceRecord.is_complete_for_research` |
| required evidence | Vendor identity, acquisition/download timestamp, package/content hash, license status |
| package field/file | `package.json` provenance fields; optional `provenance.json` |
| validation rule | `provenance_complete=false` → block |
| blocking severity | **BLOCKING** |
| current demo status | Typically **PASS** when hash + license + timestamps present |

### License

| Field | Value |
|-------|-------|
| requirement | Known, non-prohibited research license |
| current implementation | `packages/license.py` + eligibility |
| required evidence | Status ∈ {`verified`, `internal_research_only`, `redistributable`}; redistribution / research-use clarity |
| package field/file | `package.json:license_status`; optional `LICENSE.json` |
| validation rule | `unknown` / `prohibited` / `expired` → block (prohibited/expired also fail ingest) |
| blocking severity | **BLOCKING** |
| current demo status | **PASS** on redistributable pilot (still blocked by synthetic grade) |

### Checksums

| Field | Value |
|-------|-------|
| requirement | Integrity of package contents |
| current implementation | Optional `checksums.sha256` verify; directory hash for provenance |
| required evidence | Matching sha256 digests when file present |
| package field/file | `checksums.sha256` (optional) |
| validation rule | Present + mismatch → package invalid |
| blocking severity | **BLOCKING** if declared; otherwise **OPTIONAL** file |
| current demo status | **OPTIONAL** (absent on pilot) |

### Quality / anti-forgery

| Field | Value |
|-------|-------|
| requirement | No quality ERRORs; no eligibility forgery in manifest |
| current implementation | `quality/checks.py`; `eligibility_assertion_forbidden` |
| required evidence | Clean quality report; no `research_eligible` keys in package.json |
| package field/file | entire package |
| validation rule | `error_count>0` or forge keys → fail |
| blocking severity | **BLOCKING** |
| current demo status | Forge **PASS**; quality usually **PASS** on pilot bars |

---

## Minimum shopping list (external vendor)

To clear RESEARCH_ELIGIBLE you need **all** of:

1. **Licensed exchange or paid** NSE equity daily data (not yfinance/synthetic).
2. **Instrument master** with stable IDs, symbol changes, listing/delisting dates.
3. **Historical NIFTY50 (or declared universe) PIT membership** with effective dates such that the certified symbol×session set has **zero UNKNOWN**.
4. **Corporate actions**: at least splits, bonuses, dividends (verified where claiming `full_verified`); mergers as events/flags only.
5. **Delisted / terminal coverage** at least `partial` (not active-universe-only).
6. Bars aligned to a **verified NSE calendar**.
7. **Provenance + license + integrity** (hash; checksums recommended).
8. No fabricated bars / no synthetic substitution / no forged eligibility flags.

---

## Paper eligibility (data rung only)

Once `RESEARCH_ELIGIBLE` (or `PRODUCTION_CANDIDATE`) is certified:

- Paper data rung can pass the eligibility level check.
- Full `paper_eligible=true` still needs Phase 10 acceptance evidence and PRODUCTION session gates.

`DEVELOPMENT_ONLY` **always** → `paper_eligible=false`.

---

## Acceptance test

```bash
make audit-research-package
```

Implementation: `quantfund.data.packages.readiness.audit_research_package`  
(uses existing validate + `certify_research_package` — no parallel eligibility).

---

## Explicit non-goals

- Do not classify yfinance as research-grade
- Do not fabricate NIFTY50 history, delistings, or CAs
- Do not auto-reconstruct merger prices
- Do not start Phase 11 / brokers / LIVE_SEND / LLM / genetic search
