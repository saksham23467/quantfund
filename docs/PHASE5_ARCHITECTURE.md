# Phase 5 Architecture — Research-Eligible Indian Market Data

**Status:** IMPLEMENTED (D1–D10 approved; D3 = none for now).  
**Non-goals:** LLM APIs, genetic/evolutionary search, brokers, paper/live trading, fake exchange-grade providers, eligibility-gate weakening.

---

## 0. Diagnosis (current verified state)

Phase 3–3.5 already built most of the *trust machinery*. Phase 5 is about making that machinery **evidence-driven and forge-resistant**, and completing the **content/contracts** needed for a dataset to *legitimately* reach `RESEARCH_ELIGIBLE`.

### Current pilot blockers (`india_eq_pilot_phase35` / `v1_synthetic`)

```
Eligibility: DEVELOPMENT_ONLY
Blockers:
  - source_grade=synthetic is not exchange/paid research grade
  - unknown_membership_session_count=605
Also recorded:
  - delisted_coverage: none
  - universe: nifty50 / pit_partial_documented_v1 (partial_pit)
  - quality errors: 0
```

That outcome is **correct**. Phase 5 must not manufacture a different one without a real research source.

### What already exists (do not duplicate)

| Area | Existing location |
|------|-------------------|
| ResearchProvider role | `data/providers/roles.py` |
| Capabilities | `data/providers/capabilities.py` |
| Provenance | `data/providers/provenance.py` |
| Local package adapter | `data/providers/local_package.py` |
| Unconfigured fail-closed | `UnconfiguredResearchProvider` |
| Eligibility checker | `data/eligibility.py` + `data/policy.py` |
| Certification report | `data/certification.py` |
| Instrument model / identity | `data/models.py`, `data/identity.py` |
| Instrument master store | `data/instruments/master.py` |
| Terminal / delisted events | `data/instruments/delisted.py` |
| PIT membership + import | `data/universe/membership.py`, `import_membership.py` |
| CA ledger + adjust | `data/corporate_actions/*` |
| Quality engine | `data/quality/*` |
| Immutable dataset builder | `data/datasets/builder.py` |
| License notes | `DATA_LICENSE.md` |
| Certify CLIs | `scripts/certify_dataset.py`, `certify_research_dataset.py` |

Phase 4 (`quantfund.ai`, StrategySpec, ResearchRunner) **consumes** certified datasets unchanged.

---

## 1. Phase 5 objective

Move from “trust infrastructure + synthetic pilot” to:

1. A **forge-resistant** evidence chain:  
   `ProviderCapabilities` → package provenance → quality facts → `ResearchEligibilityChecker` → certificate  
2. Measurable **membership / delisted / CA coverage** (not slogans)  
3. An **external research package** contract that can carry licensed data *outside git*  
4. Keep demo/`CI` on synthetic → still `DEVELOPMENT_ONLY` unless a real package is supplied  

Eligibility states remain distinct:

| Level | Meaning |
|-------|---------|
| `development_only` | Synthetic / yfinance / incomplete PIT / quality errors / etc. |
| `research_eligible` | Evidence satisfies research bar; still not production |
| `production_candidate` | Stricter: full_pit, full_verified CA, complete delisted, etc. |

Metrics / AI strategy performance **never** promote eligibility.

---

## 2. Design principles

1. **Extend, don’t fork** — harden existing modules; avoid parallel `certification/` trees that copy `eligibility.py`.  
2. **Fail closed** — unconfigured / incomplete / forged claims → `development_only`.  
3. **Evidence over flags** — user/manifest booleans like `research_eligible=true` are ignored; only derived decisions count.  
4. **Capabilities cannot self-elevate** — package may *declare* capabilities; checker cross-validates against content hashes, coverage metrics, and policy.  
5. **Licensed data stays out of git** unless redistribution is permitted.  
6. **Phase 4 untouched** — StrategySpec / MockStrategyGenerator / interpreter semantics stay as-is.

---

## 3. Real data provider boundary

### Keep

- `ResearchProvider` ABC in `roles.py`  
- `ProviderCapabilities`, `ProvenanceRecord`  
- `LocalResearchPackageProvider` as vendor-neutral ingest path  
- `UnconfiguredResearchProvider` fail-closed  

### Harden (Phase 5)

Extend `ProviderCapabilities` (additive fields):

| Field | Purpose |
|-------|---------|
| `identity_coverage` | ISIN/symbol-history quality |
| `supported_exchanges` | e.g. `["NSE"]` |
| `supported_date_range` | structured start/end |
| `redistribution_allowed` | bool \| unknown |
| `license_status` | enum: `unknown` / `prohibited` / `internal_research_only` / `redistributable` |
| `capability_attestation_hash` | hash of declared capabilities blob |
| `authority_evidence_refs` | list of source refs (contracts, product docs) — **not** a trust auto-grant |

**Rule:** Returning bars ≠ trustworthy.  
`can_satisfy_research_eligibility_source_bar()` remains necessary but **not sufficient**.

### Do **not** create

- A fake “NSEExchangeProvider” that invents prints  
- A scraper-based production provider  
- A path that sets `source_grade=exchange` because schema validation passed  

### Integration contract

```
External Research Package (local disk / licensed store)
        ↓
ResearchPackageValidator  (NEW — structural + checksum + capability consistency)
        ↓
LocalResearchPackageProvider (EXISTING, extended)
        ↓
ingest_bars_raw (EXISTING provenance)
        ↓
DatasetBuilder + quality + ResearchEligibilityChecker (HARDENED)
        ↓
certificate (derived)
```

Vendor SDKs (if any later) wrap into this package format; FeatureEngine / Strategy / ResearchRunner never import vendor SDKs.

---

## 4. Source options analysis (decision input)

> None of these are “approved as exchange-grade” by this document. Approval requires license evidence + capability attestation.

| Option | Authority | Historical depth | CA | Delisted | NIFTY50 PIT | License / redistribution | API / bulk | Complexity | Can satisfy gates? |
|--------|-----------|------------------|----|----------|-------------|--------------------------|------------|------------|--------------------|
| **A. NSE official / licensed** | Highest (exchange) | Product-dependent | Best when licensed | Best when licensed | Index membership via NSE Indices products / archives — separate license | Strict; usually no public redistrib | Often file/FTP/vendor channel | High (legal + ops) | **Yes, if licensed product covers CA+delisted+PIT needs** |
| **B. Licensed redistributor** (e.g. enterprise India equity vendors) | Derived; must document authority chain | Often deep | Vendor-dependent; must audit | Vendor-dependent | Often sold as index history add-on | Contractual; usually no git commit | REST/SFTP/SDK | Medium–high | **Yes if capabilities verified and license allows research storage** |
| **C. Broker historical API** | Broker ≠ exchange authority by default | Often limited / survivor-biased | Often incomplete | Often incomplete | Rarely official PIT | Broker ToS; research use varies | API | Medium | **Usually no** for full research_eligible unless broker is an authorized redistributor *and* coverage proven |
| **D. Other exchange-authorized** | Case-by-case | Case-by-case | Case-by-case | Case-by-case | Case-by-case | Case-by-case | Case-by-case | Case-by-case | Only with written authority + coverage proof |
| **yfinance (status quo)** | Non-exchange | Vendor-dependent | Partial/unreliable | Poor | None official | ToS; not research authority | API | Low | **Never** `research_eligible` |
| **Synthetic fixtures** | None | N/A | Synthetic | None | Partial documented events only | Redistributable for CI | N/A | Low | **Never** `research_eligible` |
| **Web scraping** | None / fragile | Unreliable | Unreliable | Unreliable | Unreliable | Legal/ToS risk | Ad hoc | High risk | **Rejected** as production acquisition |

### Recommended Phase 5 dependency decision

**Default path (no credentials in repo):**

1. Harden package contract + forge-resistant certification.  
2. Keep CI/demo on synthetic → `DEVELOPMENT_ONLY`.  
3. Treat **B (licensed redistributor)** or **A (NSE licensed product)** as the *future* content source, ingested as an external research package.  
4. Explicitly **reject** yfinance/scraping/broker-as-default for research eligibility.  

**Decision required from you before implementation** (see §17): which real source (if any) will be configured in your environment, and whether its license allows local storage of RAW bars.

---

## 5. Instrument master

### Keep

- `Instrument` + `SymbolHistoryEntry`  
- `InstrumentMasterStore` (immutable versions)  
- `apply_symbol_change` / `check_instrument_identity`  

### Phase 5 additions

1. **Identity policy document** in code: permanent id = `exchange:ISIN` when ISIN known; never ticker-alone.  
2. **Collision registry checks** across master versions (ERROR if same ISIN maps to conflicting economic entities without history).  
3. **Terminal linkage**: `delisting_date` must reconcile with `TerminalEvent` ledger (WARNING/ERROR by policy).  
4. **Provider symbol map validation**: mismatch between package bars symbol and master mapping → ERROR.  
5. Tests proving rename ≠ new instrument (same `instrument_id` across symbol_history).

No automatic merger→successor price stitching.

---

## 6. Delisted / terminal events

### Keep

- `TerminalEvent` / `TerminalEventStore` / `TerminalEventType`  

### Phase 5 additions

1. Align naming with design intent (`InstrumentTerminalEvent` as alias or documented synonym — prefer **extend existing** `TerminalEvent`, don’t fork).  
2. Required fields already mostly present; add optional `last_trade_date`, `source_ref` if missing.  
3. Coverage metric:  
   - `delisted_coverage = none | partial | complete | unknown`  
   - computed from: presence of ledger + fraction of instruments with terminal closure in declared universe/history  
4. Quality: bars after `delisting_date` / after terminal event → ERROR.  
5. Never invent post-delist prices.

**Production_candidate** continues to require `delisted_coverage=complete` (existing policy).

---

## 7. Point-in-time NIFTY50 membership

### Keep

- `UniverseMembership`, `was_member` TRUE/FALSE/UNKNOWN  
- Partial documented reconstitutions (`pit_partial_documented_v1`)  
- CSV/JSON import  

### Phase 5 pipeline (new orchestration, existing models)

```
Source archives (niftyindices / licensed index history)
        ↓
membership_import (reproducible, versioned)
        ↓
UniverseVersion (partial_pit | full_pit)
        ↓
coverage.py metrics
        ↓
certification facts
```

### New coverage metrics (`data/universe/coverage.py` — NEW)

For a declared trading calendar ∩ dataset date range ∩ instrument set:

| Metric | Definition |
|--------|------------|
| `known_membership_sessions` | sessions where answer ∈ {TRUE, FALSE} |
| `unknown_membership_sessions` | sessions where answer = UNKNOWN |
| `membership_coverage_ratio` | known / (known+unknown) |

Rules:

- Today’s constituents never projected backward.  
- Untracked name under `partial_pit` remains UNKNOWN (already implemented).  
- `full_pit` claim requires evidence that the roster is complete for the coverage window — not a boolean flip.  
- Import writes a **new** `universe_version` (fix immutability for membership store — currently weaker than dataset builder; Phase 5 should make membership versions immutable like datasets).

---

## 8. Corporate-action coverage

### Keep

- Split/bonus/dividend adjust policy; RAW immutable  
- Merger/demerger `requires_manual_treatment`  

### Phase 5: structured CA coverage report

Replace/augment single string with typed breakdown:

```yaml
corporate_action_coverage:
  splits: full_verified | partial | none | unknown
  bonuses: ...
  dividends: ...
  symbol_changes: ...
  mergers: partial | none | unknown | unsupported
  demergers: ...
  overall: splits_bonus_dividends | full_verified | partial | none  # derived
```

Merger/demerger handling modes (explicit, no invented formulas):

- `verified_mapping` (manual, attested)  
- `manual_review_required`  
- `unsupported`  

Eligibility policy maps `overall` (+ optionally per-type floors) — **no silent OHLC invention**.

---

## 9. Data quality (adversarial expansion)

Extend `run_quality_checks` with additional ERROR/WARNING codes (additive):

| Check | Severity |
|-------|----------|
| Bar on verified closed session (unexpected presence) | ERROR/WARNING by policy |
| Timezone / session-date inconsistency | ERROR |
| Future membership visibility (as-of leak) | ERROR |
| Post-delisting bars | ERROR |
| CA date inconsistencies (ex_date < listing, etc.) | ERROR/WARNING |
| Raw mutation / checksum mismatch vs package | ERROR |
| Provider provenance mismatch vs manifest | ERROR |
| Capability forgery attempts (grade vs provider_id) | ERROR |
| Wrong calendar hiding missing session | already demonstrated; keep as adversarial tests |

Wrong calendar / universe / CA ledger must fail loudly in certification, not “look clean.”

---

## 10. Certification hardening (forge resistance)

### Keep

- `ResearchEligibilityChecker`  
- `DatasetCertificationFacts`  
- `certify_*` scripts  

### Phase 5 rules

Eligibility is **derived** from:

1. Provider capabilities **bound to package content hash**  
2. Quality report  
3. Membership coverage metrics  
4. CA coverage breakdown  
5. Delisted / identity metrics  
6. Calendar verification  

**Rejected forgery patterns (tests):**

- Editing `manifest.json` to set `research_eligibility=research_eligible`  
- Setting `source_grade=exchange` on synthetic/yfinance package  
- Flipping `exchange_authority=true` without capability attestation consistency  
- Claiming `full_pit` while `unknown_membership_sessions > 0`  
- Certificate JSON edited after issue (checksum of facts payload)

Implementation approach:

- Builder writes `certification.json` with `facts_hash` + `decision`  
- Re-certify recomputes facts from package/dataset content; mismatch → ERROR  
- Manifest gate already force-downgrades non_exchange/synthetic; keep and strengthen with capability cross-check  

---

## 11. Explicit RESEARCH_ELIGIBLE gates (not weakened)

Documented bar (policy-configurable, defaults):

**RESEARCH_ELIGIBLE requires all of:**

1. `source_grade ∈ {exchange, paid}` **and** capability source-bar pass (`exchange_authority` or paid)  
2. Provider ≠ synthetic/yfinance path  
3. `calendar_verified=true`  
4. Universe completeness ∈ `{partial_pit, full_pit}` **and** `unknown_membership_sessions == 0` for the certified trading set  
5. Membership coverage ratio ≥ policy threshold (default 1.0 for traded set)  
6. CA `overall` ∈ `{splits_bonus_dividends, full_verified}` (or stricter per-type if configured)  
7. Instrument identity issues == 0 (ERROR-class)  
8. Delisted coverage ∈ policy allow-list for research (default: at least `partial` for research_eligible; `complete` for production)  
9. Quality mandatory ERROR count == 0  
10. Provenance complete (provider, timestamps, request params, content hashes, license_status known≠prohibited for stored RAW)  
11. Dataset immutable + reproducible manifest  
12. Capability attestation consistent with package hash  

**PRODUCTION_CANDIDATE** additionally:

- `full_pit`  
- CA `full_verified` (incl. documented stance on mergers/demergers)  
- `delisted_coverage=complete`  
- optional zero-warning policy  

---

## 12. External research package format

Design (validated by NEW `ResearchPackageValidator`):

```
research_package/
  package.json              # capabilities + license + ids (NOT eligibility decision)
  provenance.json
  checksums.sha256
  instruments.parquet|json
  bars/                     # per instrument partitions
  corporate_actions.parquet|json
  universe_membership.parquet|json
  terminal_events.parquet|json
  calendar_reference.json   # points to calendar_id/version (NSE_EQ), does not replace calendars/
  LICENSE_NOTES.md          # optional human text
```

Rules:

- Package declares capabilities; **does not** declare final eligibility.  
- Bars optional in git; CI uses synthetic fixture package only.  
- Validator verifies checksums before DatasetBuilder.  

This extends `LocalResearchPackageProvider` rather than replacing it.

---

## 13. Integration with Phase 4

```
[Phase 5] Research package → certify → RESEARCH_ELIGIBLE (only if evidence)
                ↓
[Phase 2/4] FeatureEngine → StrategySpec (AI/mock) → validator → interpreter
                ↓
         ResearchRunner (sealed TEST) → registry → scoring
```

No StrategySpec semantic changes required.  
No AI self-selection.  
`development_only` still forces `accepted=False` / exploratory.

---

## 14. Modules that must remain unchanged (behavior contracts)

Do not rewrite these contracts:

| Module / guarantee |
|--------------------|
| Next-bar-open execution / no same-bar fills |
| RAW execution prices |
| Strategy / StrategyContext / Signal→Order→Fill separation |
| StrategySpec Rule semantics + Expr additive model |
| AI package isolation (generator ≠ evaluator) |
| ResearchRunner does not generate strategies |
| Sealed TEST |
| UNKNOWN membership non-trading |
| `ResearchEligibilityChecker` hardness (no metric promotion) |
| Existing 154 tests’ public APIs |

---

## 15. Proposed files create / modify

### Create

| Path | Role |
|------|------|
| `src/quantfund/data/providers/package_validator.py` | Research package structural + checksum + capability consistency |
| `src/quantfund/data/universe/coverage.py` | membership coverage metrics |
| `src/quantfund/data/certification/forge.py` | facts hashing / anti-forgery helpers *(or functions inside existing `certification.py` — prefer single module unless size warrants package)* |
| `src/quantfund/data/corporate_actions/coverage.py` | per-type CA coverage derivation |
| `scripts/validate_research_package.py` | CLI package validation |
| `scripts/run_phase5_demo.py` | demo (expect DEVELOPMENT_ONLY without real package) |
| `tests/unit/test_phase5_*.py` | ≥30 tests (provider, identity, pit, certification, adversarial) |
| `tests/fixtures/phase5/` | synthetic package variants for forge/PIT/delist tests |
| `docs/PHASE5_DATA_SOURCES.md` | living source/license decision log |

### Modify (extend)

| Path | Change |
|------|--------|
| `providers/capabilities.py` | additive capability fields |
| `providers/local_package.py` | richer package layout; refuse forged grades |
| `providers/roles.py` | docstring/contract only unless needed |
| `instruments/delisted.py` | optional fields + coverage helpers |
| `instruments/master.py` | immutability already; cross-checks |
| `universe/membership.py` / store | immutable version saves |
| `universe/import_membership.py` | provenance fields `source_ref` |
| `quality/checks.py` | adversarial codes |
| `eligibility.py` / `policy.py` | explicit coverage thresholds; CA breakdown awareness |
| `certification.py` | richer report + facts_hash |
| `datasets/builder.py` | wire coverage + anti-forgery |
| `datasets/manifest.py` | store coverage metrics; still force-dev on synthetic |
| `DATA_LICENSE.md` | structured license record template |
| `Makefile` | `phase5-demo`, `validate-research-package` |
| `README.md` / `ASSUMPTIONS.md` | Phase 5 status |

### Explicitly **not** creating (would duplicate)

- `research_provider.py` (use `roles.py`)  
- Parallel `certification/` package unless `certification.py` grows too large  
- Second backtester / second eligibility checker  

---

## 16. Test plan (≥30 new tests)

### Provider
1. Capability declaration required  
2. Unconfigured fail-closed  
3. Provenance present  
4. Synthetic cannot claim exchange  
5. yfinance cannot claim research-eligible source bar  
6. Editing capability JSON to `exchange` without attestation consistency fails  

### Identity
7. ISIN-stable id across rename  
8. Symbol change preserves instrument_id  
9. Duplicate identity collision ERROR  
10. Delisting date inconsistency ERROR  

### PIT
11. Reconstitution enter/leave  
12. UNKNOWN for untracked  
13. Coverage ratio computation  
14. No backward projection of today’s list  
15. `full_pit` claim rejected when unknowns remain  

### CA
16. Split/bonus/dividend verified path  
17. Merger unsupported / manual_review  
18. Coverage breakdown derivation  
19. Future CA visible → ERROR  

### Certification / forgery
20. Synthetic → development_only  
21. Incomplete PIT → development_only  
22. Missing delisted → blocks production_candidate  
23. Manual `research_eligible` in manifest ignored/overwritten  
24. Facts hash mismatch detected  
25. Certificate recompute deterministic  

### Integrity / adversarial
26. Checksum mismatch  
27. Immutable raw package overwrite rejected  
28. Wrong calendar hides session → adversarial test  
29. Post-delisting bars ERROR  
30. Future membership leak ERROR  
31. Provider provenance mismatch  
32. Unexpected bar on holiday  
33. Phase 4 pipeline still DEVELOPMENT_ONLY on synthetic  
34. Existing research runner sealed TEST unchanged  

---

## 17. Implementation order (after approval)

1. Capabilities + package validator + anti-forgery facts hash  
2. Instrument identity + terminal coverage metrics  
3. PIT import immutability + `coverage.py`  
4. CA coverage breakdown  
5. Adversarial quality checks  
6. Eligibility/policy wiring (stricter explicitness, **not** weaker)  
7. Builder/certify script updates  
8. Phase 4 integration smoke (no Spec changes)  
9. Tests (≥30)  
10. `make phase5-demo` (expect DEVELOPMENT_ONLY without real package)  

---

## 18. Phase 5 demo contract

```
make phase5-demo
```

Uses redistributable synthetic / phase35 package unless `QUANTFUND_RESEARCH_PACKAGE` points to a validated external package.

Prints:

- provider / source grade / license_status  
- calendar verified  
- universe coverage metrics  
- CA coverage breakdown  
- delisted coverage  
- quality errors/warnings  
- eligibility + blockers  

**Expected without real licensed data:** `DEVELOPMENT_ONLY`.  
That is success.

---

## 19. Approval decisions required

Please approve or revise each item before any coding:

| # | Decision | Recommendation |
|---|----------|----------------|
| **D1** | Proceed with **extend-existing** architecture (no duplicate ResearchProvider module)? | **Approve** |
| **D2** | Default acquisition path = **external research package** + `LocalResearchPackageProvider`; no scraper; yfinance never research-eligible? | **Approve** |
| **D3** | Which real source will you configure later: **A NSE licensed**, **B redistributor**, **C broker**, **none for now**? | **Need your choice** (default: **none for now**) |
| **D4** | RESEARCH_ELIGIBLE requires `unknown_membership_sessions == 0` for the certified traded set? | **Approve** (keeps current hardness) |
| **D5** | RESEARCH_ELIGIBLE requires delisted coverage at least `partial`; production requires `complete`? | **Approve** |
| **D6** | CA eligibility uses **overall + optional per-type floors**; mergers/demergers never auto-priced? | **Approve** |
| **D7** | Anti-forgery via recomputed `facts_hash` (manifest booleans non-authoritative)? | **Approve** |
| **D8** | Put coverage helpers in `universe/coverage.py` + `corporate_actions/coverage.py` rather than a new top-level package? | **Approve** |
| **D9** | CI/demo remain synthetic/`DEVELOPMENT_ONLY` unless external package env var set? | **Approve** |
| **D10** | No LLM / genetic search / brokers in Phase 5? | **Approve** |

---

## 20. Success criteria (post-implementation)

- Existing **154** tests remain green  
- ≥ **30** new Phase 5 tests  
- No eligibility gate weakened  
- No fake exchange-grade provider  
- No improper licensed data in git  
- PIT/delisted/CA coverage measurable and honest  
- Eligibility derived, not asserted  
- Phase 4 demo still works  
- `make phase5-demo` → `DEVELOPMENT_ONLY` without real data  

---

**STOP.** Awaiting your approval of D1–D10 (especially **D3** source choice) before implementation.
