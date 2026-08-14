# Phase 6 Architecture — Quantitative Strategy Research Campaign

**Status:** IMPLEMENTED (C1–C8 approved).  
**Non-goals:** LLM connection, genetic/evolutionary search, brokers, paper/live trading, eligibility-gate weakening, manufacturing `RESEARCH_ELIGIBLE` data, accepting strategies on synthetic/yfinance.

Phase 5 remains the **sole source of truth** for research eligibility. Metrics, scores, and generators never promote a dataset.

---

## 0. Repository assessment (verified)

### What exists (reuse — do not fork)

| Layer | Location | Role |
|-------|----------|------|
| FeatureEngine / FeatureSpec / library | `features/` | Point-in-time features (`asof(T)`) |
| StrategySpec + Expr + validator + interpreter | `strategies/spec/` | Sandboxed DSL only |
| Baselines | `strategies/baselines/`, `examples/buy_and_hold.py` | Deterministic comparators |
| MockStrategyGenerator + LLM stub | `ai/` | Generate Specs; LLM unconnected |
| Genealogy + canonical hash | `ai/genealogy.py` | Family / parent / mutation metadata |
| StrategyResearchPipeline | `ai/pipeline.py` | Generate → validate → dedupe → interpret → evaluate; **always** `sealed_evaluation=False` |
| ExperimentConfig / Result + hashing | `research/experiment.py` | Frozen per-experiment config |
| ResearchRunner | `research/runner.py` | Evaluator only; clamps eligibility; sealed TEST |
| Splits / sealed TEST | `research/splits.py` | `SealedTestSetError`; unlock only with sealed flag |
| Walk-forward | `research/walkforward.py` | Window generation |
| Robustness | `research/robustness.py` | Cost/slippage sensitivity |
| score_policy_v1 | `research/scoring.py` | Composite score; hard rejects; score ≠ override |
| DSR + trial payload | `research/multiple_testing.py` | Deflated Sharpe |
| Baselines compare | `research/baselines_compare.py` | Buy-and-hold + cash |
| Per-experiment report | `research/report.py` | JSON/TXT artifacts |
| ExperimentRegistry | `storage/registry.py` | SQLite + artifacts; trial counters increment-only |
| DatasetReader / Manifest / Certification | `data/datasets/`, `eligibility.py`, `certification.py` | Phase 5 gates |
| BacktestEngine / costs / slippage / risk | `backtest/`, `risk/` | Next-bar-open; equity delivery costs |

### Current gaps (Phase 6 must add)

| Gap | Why needed |
|-----|------------|
| No `ResearchCampaignConfig` | Experiments exist; campaigns (budgets, purpose, freeze) do not |
| No candidate pool / funnel stages | Pipeline is one-shot batch; no cheap screen → validate → seal |
| No campaign-level sealed TEST FSM | Per-experiment seal exists; no campaign freeze / contamination ledger |
| No search-space budget object | Only `number_of_candidates` on `GenerationRequest` |
| No campaign-scoped trial accounting | Family counters exist; no `campaign_id` / immutable campaign ledger |
| Registry not append-only | `INSERT OR REPLACE` — Phase 6 needs audit events, not silent overwrite of science |
| Cost/slippage config strings unused | Runner hardcodes equity delivery + 5 bps — must wire or document |
| No campaign report | Only per-experiment reports |
| No `make phase6-demo` | — |

### Hard contracts that must not change

- Phase 5 `ResearchEligibilityChecker` gates
- Generator ≠ evaluator ≠ acceptor
- TEST sealed until explicit sealed evaluation
- `development_only` → never `accepted`
- StrategySpec: no eval/exec/imports/network/filesystem
- Next-bar-open RAW execution
- `score_policy_v1` weights unchanged unless explicitly introducing `score_policy_v2`

---

## 1. Core objective

Answer:

> Does a candidate strategy demonstrate evidence of a robust, statistically credible edge on unseen Indian-market data after costs, slippage, multiple testing, and realistic execution assumptions?

**Outcome vocabulary (campaign-level):**

| Label | Meaning |
|-------|---------|
| `exploratory` | Ran on `DEVELOPMENT_ONLY` or incomplete funnel; no scientific claim |
| `candidate` | Structurally valid, in pool, not yet validated |
| `validation_result` | Validation metrics recorded; not sealed |
| `sealed_test_result` | One-shot TEST evaluation after seal |
| `rejected` | Failed a hard gate or policy threshold (reason required) |
| `accepted_research_candidate` | Passed all hard gates on `RESEARCH_ELIGIBLE` data; still not live trading |

An attractive backtest alone never implies acceptance.

---

## 2. Architecture (reuse kernel, add campaign layer)

```
Research Campaign
      │
      ├── Dataset (certified via Phase 5) ──────────── ResearchEligibilityChecker
      ├── Feature Library (FeatureEngine)
      ├── Baselines (existing)
      ├── Candidate Generator (human / Mock / future LLM adapter)
      ├── Candidate Validator (StrategySpecValidator)
      ├── CandidatePool + SearchSpace budgets
      ├── Cheap Screening (TRAIN/VALIDATION only)
      ├── Experiment Scheduler → ResearchRunner
      ├── Robustness + Walk-Forward (existing engines)
      ├── Multiple Testing (DSR + campaign trial ledger)
      ├── Sealed TEST (campaign FSM + ChronologicalSplit)
      └── CampaignReport
```

**Separation:**

| Concern | Owner |
|---------|--------|
| GENERATION | `StrategyGenerator` / human Specs — never sees TEST or acceptance |
| EVALUATION | `ResearchRunner` — metrics, DSR, score components |
| ACCEPTANCE | `CampaignAcceptancePolicy` (new) calling existing score hard gates + campaign gates — never the generator |

`StrategyResearchPipeline` remains the **batch generate→evaluate** helper for early funnel stages.  
`CampaignRunner` (new) owns budgets, stages, seal, and final decision.

---

## 3. Dataset requirement

| Campaign purpose | Required eligibility | Can produce `accepted_research_candidate`? |
|------------------|----------------------|---------------------------------------------|
| `exploratory_development` | any (incl. `DEVELOPMENT_ONLY`) | **No** |
| `research` | `research_eligible` or `production_candidate` | Yes, if all gates pass |
| `production_probe` | `production_candidate` preferred | Same as research + production notes |

Rules:

1. Campaign loads `DatasetManifest` + certification; `certified_eligibility` is injected into every experiment (runner already clamps upward claims).
2. Exploratory campaigns stamp all reports `DEVELOPMENT_ONLY` / `FINAL RESEARCH CLAIMS: NONE`.
3. No path graduates a strategy from development → accepted because metrics look good.
4. Changing `dataset_version` after campaign start → hard fail (config hash mismatch).

---

## 4. `ResearchCampaignConfig` (new, frozen)

Versioned, immutable after `RUNNING` begins. Canonical hash via existing `hash_json`.

Minimum fields:

| Field | Notes |
|-------|--------|
| `campaign_id` | UUID label (excluded from scientific hash like `experiment_id`) |
| `campaign_version` | Explicit version string |
| `purpose` | `exploratory_development` \| `research` \| `production_probe` |
| `dataset_id` / `dataset_version` | Must match certified package |
| `universe_id` / `universe_version` | PIT universe |
| `calendar_id` / `calendar_version` | From dataset lineage |
| `feature_set` | List of feature requests / allowlist |
| `candidate_generator` | `human` \| `mock` \| `llm_adapter` (llm still unconnected) |
| `strategy_family` / `family_id` | Multiple-testing family |
| `search_space` | See §7 |
| `parameter_budget` | Max distinct param combinations |
| `experiment_budget` | Max `ResearchRunner.evaluate` calls |
| `candidate_budget` | Max unique StrategySpec hashes admitted to pool |
| `runtime_budget_seconds` | Soft wall-clock stop |
| `train` / `validation` / `test` periods | Maps to `SplitConfig` |
| `walkforward_config` | Existing `WalkForwardConfig` or null |
| `cost_model` / `slippage_model` | Must be **wired** to runner (fix gap) |
| `initial_capital` | Default ₹100,000 |
| `benchmark` | e.g. buy-and-hold universe / cash |
| `selection_criterion` | Declared before TEST (e.g. `validation_sharpe`) |
| `score_policy` | Default `score_policy_v1` |
| `robustness_policy_id` | Versioned policy (new thin wrapper over existing suite) |
| `screening_policy_id` | Versioned cheap screen |
| `multiple_testing_policy_id` | How trials aggregate |
| `acceptance_policy_id` | Hard gates for final accept |
| `random_seed` | Determinism |
| `code_version` | Platform version |
| `created_at` | Audit only (not in scientific hash) |

**Immutability:** Persist config + `campaign_hash` under `artifacts/campaigns/{campaign_id}/`. Any mutate attempt after `RUNNING` raises. Resume must load the same hash.

---

## 5. Candidate generation

Supported sources (no LLM wire-up in Phase 6 implementation):

| Source | Interface |
|--------|-----------|
| A. Human-authored | Load StrategySpec JSON → validator |
| B. Mock | Existing `MockStrategyGenerator` + `GenerationRequest` |
| C. Future LLM | Existing `LLMStrategyGenerator` stub only |

Every admitted candidate record:

```
candidate_id, campaign_id, StrategySpec, strategy_hash,
genealogy, generator_metadata, created_at, stage
```

**Dedup:** `canonical_strategy_hash` before evaluation; duplicates increment `n_duplicates` but **do not** consume experiment budget (they may consume a tiny “hash check” counter for audit). Equivalent Specs share one trial slot.

Budgets enforced in order: structural validity → dedup → candidate_budget → screening → experiment_budget.

---

## 6. Controlled search space (no unrestricted HPO)

`SearchSpace` (new) declares finite dimensions with explicit caps:

| Dimension | Cap examples |
|-----------|--------------|
| Features | Subset of allowlisted library names |
| Thresholds | Discrete grid only |
| Lookbacks | Discrete set (e.g. {5,10,20,60}) |
| Entry/exit rule templates | Finite template IDs |
| Sizing / risk | Within platform ceilings already in Spec |

Forbidden:

- Infinite / continuous unbounded search
- Hidden optimizer loops
- TEST-informed generation
- Generator reading evaluation results mid-campaign (no feedback bandit in v1)
- Arbitrary code

Phase 6 v1 search = **enumerated / mock-generated** within budgets — not genetic algorithms.

---

## 7. Research funnel & data access

```
Generated
   → Structurally Valid      (validator; no market data required)
   → Deduplicated            (hash; TRAIN unused)
   → Cheap Screening         (TRAIN only, or short TRAIN slice)
   → Validation              (VALIDATION split; no TEST)
   → Robustness              (VALIDATION-centric; child experiments)
   → Walk-Forward            (dev bars only; no TEST)
   → SEALED                  (freeze Spec/params/splits/costs)
   → Sealed TEST             (one shot)
   → Final Research Decision
```

| Stage | May access TRAIN | VAL | TEST | Baselines |
|-------|------------------|-----|------|-----------|
| Screen | Yes (limited) | Optional light | **No** | Optional |
| Validation | No (or for features warmup only) | Yes | **No** | Yes |
| Robustness | Per policy | Yes | **No** | Yes |
| Walk-forward | Windows on dev bars | Windows | **No** | Yes |
| Sealed TEST | Frozen | Frozen | **Yes once** | Yes |

Most important: TEST inaccessible until candidate (and campaign policy) is `SEALED`.

---

## 8. Cheap screening (`screening_policy_v1`)

Versioned thresholds (document in config; no silent changes):

Proposed defaults (tunable, frozen per campaign):

- `min_trades` (e.g. 5 on screen window)
- `max_drawdown` ceiling (e.g. 0.40) — catastrophic filter only
- `require_finite_metrics` — no NaN Sharpe
- `max_cost_drag_fraction` of gross profit (viability)
- Optional: beat cash on screen window (not TEST)

Screening **never** uses TEST. Fail → `rejected` with reason `failed_screening:{code}`.

---

## 9. Baselines

Every campaign runs (or loads cached) baselines via existing `baselines_compare`:

- Buy-and-hold
- Cash
- Existing deterministic strategy baselines (MA/momentum/mean-rev/vol) when in scope
- Index/benchmark when dataset provides it

Report absolute + excess vs benchmark for: return, Sharpe, max DD, turnover, costs, slippage, win rate, trades, exposure, volatility. **Never rank by CAGR alone.**

---

## 10. Walk-forward aggregation (campaign-level)

Reuse `generate_walkforward_windows` / runner WF path. Aggregate across windows:

- median / mean window Sharpe
- fraction positive windows
- fraction beating benchmark
- worst window DD / excess return
- qualitative regime notes (metadata only)

**Do not** treat a stitched equity curve as an independent statistical sample for DSR `n_obs`.

---

## 11. RobustnessPolicy (versioned wrapper)

Reuse `run_robustness_suite`. `robustness_policy_v1` documents required cases:

- Costs: 0.5× / 1× / 2× / 3×
- Slippage: baseline and +N bps
- Parameter perturbations (discrete neighbors in search space)
- Boundary shifts (± few sessions) when data allows
- Subperiod split of validation
- Optional vol-regime split if features available

Fragile definition remains documented (existing: return sign-flip under ≥2× costs). Campaign acceptance requires `pass_rate ≥` policy floor.

---

## 12. Multiple-testing model

### Counters (campaign ledger — append-only events)

| Counter | When incremented |
|---------|------------------|
| `n_candidates_generated` | Generator/human emit |
| `n_structurally_valid` | Validator pass |
| `n_unique_strategies` | New strategy hash in pool |
| `n_duplicates` | Hash collision |
| `n_screened` / `n_screen_passed` | Screen stage |
| `n_parameter_combinations` | Distinct param sets evaluated |
| `n_experiments` | Each `ResearchRunner.evaluate` / registry put |
| `n_validation_trials` | Validation-purpose experiments |
| `n_test_evaluations` | Sealed TEST unlocks (must be ≤1 per sealed candidate) |
| `n_families` | Distinct `family_id`s |

Reuse `deflated_sharpe_ratio` with **campaign-visible** `n_trials` (not understated). Prefer max(family trials, campaign validation trials) per declared `multiple_testing_policy_v1`.

### Safeguards

- No silent trial reset
- No deleting failed experiments (tombstone status only)
- No repeated TEST access (`n_test_evaluations` gate)
- Selection criterion frozen in campaign config before seal
- Cherry-picking across campaigns requires declaring prior campaigns in report (manual honesty field in v1)
- Registry: add `campaign_events` append-only table; stop using replace for scientific rows of a finalized campaign (see §19)

---

## 13. Sealed TEST state machine

### Campaign states

```
DRAFT → READY → RUNNING → (optional PAUSED) → SEALING → TEST_PHASE → FINALIZED
                              ↘ FAILED / ABORTED
```

### Candidate states

```
GENERATED → VALID → DEDUPED → SCREENED → VALIDATION → ROBUST → WALKFORWARD
    → SEALED → TEST_EVALUATED → ACCEPTED | REJECTED
```

Contamination edges:

- Any TEST bar access while candidate not `SEALED` → `CONTAMINATED` (campaign + candidate)
- Parameter/feature/split/cost change after `SEALED` → illegal
- “Just one more test” → rejected by FSM (`n_test_evaluations >= 1`)

Implementation: wrap existing `ChronologicalSplit.unlock_test(sealed_evaluation=True)` behind `CampaignTestSeal` that checks candidate+campaign state first.

---

## 14. Acceptance

`CampaignAcceptancePolicy` (evaluator-owned) requires **all**:

1. Dataset `research_eligible` or `production_candidate` (not development)
2. Valid StrategySpec; no leakage / UNKNOWN membership trades
3. Validation success per selection criterion
4. Robustness policy pass
5. Walk-forward consistency floor (if WF enabled)
6. Cost/slippage sensitivity acceptable
7. Candidate `SEALED` then exactly one TEST evaluation
8. Declared selection criterion unchanged since READY
9. Multiple-testing / DSR recorded
10. No contamination
11. `score_policy_v1` hard rejects empty
12. Score **cannot** override any hard rejection

Generator cannot set `metadata.accepted` (already forbidden).

---

## 15. Strategy score

- Default: **`score_policy_v1`** — do not silently change weights.
- If campaign needs different weights/thresholds → introduce explicit **`score_policy_v2`** with justification in campaign notes.
- Score informs ranking among non-rejected candidates; never overrides hard gates.

---

## 16. Genealogy

Extend existing `StrategyGenealogy` usage:

```
campaign_id → parent strategy → mutation/generation → child Spec
    → experiments → validation → robustness → test → final decision
```

Registry/campaign report must answer: why created, parent, feature/param diffs, related trials, family size.

Mock remains `generation_number=0` unless human/mutation tool sets otherwise — still no genetic search loop.

---

## 17. Campaign report

Machine-readable `campaign_report.json` + human `campaign_report.txt`:

1. **Dataset** — source, license/provenance, eligibility, calendar, universe, PIT/CA/delisted coverage (from Phase 5 certification facts)
2. **Campaign** — hash, code version, config, budgets, trial counts
3. **Candidates** — generated / valid / duplicate / screened / evaluated / robust / sealed / tested / accepted / rejected
4. **Performance** — vs baselines (full metric set)
5. **Robustness / walk-forward**
6. **Statistical integrity** — n_trials, DSR, contamination, selection criterion
7. **Final decisions** — every candidate explicit accept/reject reason

Exploratory banner mandatory when eligibility ≠ research_eligible.

---

## 18. Failure recovery

| Failure | Behavior |
|---------|----------|
| Crashed experiment | Status `failed`; resume skips completed `config_hash` via `already_run` |
| Corrupted artifact | Recompute only if config hash + code version match; else fail closed |
| Duplicate campaign_id | Reject create |
| Partial campaign | Resume from last event; cannot alter config |
| Inconsistent config hash | Abort |
| Missing / changed dataset | Abort |
| Registry failure | No silent continue; surface error |

Never silently rerun with different assumptions.

---

## 19. Parallelism & registry hardening

v1: **single-machine, deterministic, SQLite, local artifacts**.

Before any workers:

- Document trial-count atomicity (`BEGIN IMMEDIATE` transactions)
- Append-only `campaign_events`
- Prefer insert-once for finalized experiment rows (no scientific overwrite)

No Ray/Dask/Spark in Phase 6.

---

## 20. Security (preserve Phase 4)

- No eval/exec/imports/network/filesystem/subprocess from Spec
- No secrets / broker credentials
- No self-acceptance
- No dataset mutation from campaign code paths
- Generator never receives TEST or acceptance signals

---

## 21. Proposed files (after approval)

### Create

| Path | Role |
|------|------|
| `src/quantfund/research/campaign.py` | `ResearchCampaignConfig`, hashing, purpose |
| `src/quantfund/research/campaign_state.py` | Campaign + candidate FSM |
| `src/quantfund/research/candidate_pool.py` | Pool, dedupe, budgets |
| `src/quantfund/research/search_space.py` | Finite search dimensions |
| `src/quantfund/research/screening.py` | `screening_policy_v1` |
| `src/quantfund/research/test_seal.py` | Seal + contamination guards |
| `src/quantfund/research/campaign_runner.py` | Orchestrator |
| `src/quantfund/research/campaign_report.py` | Campaign report writer |
| `src/quantfund/research/acceptance.py` | Acceptance policy (evaluator-owned) |
| `scripts/run_phase6_demo.py` | Infra demo on DEVELOPMENT_ONLY |
| `tests/unit/test_phase6_*.py` | ≥40 tests |
| `tests/integration/test_phase6_campaign.py` | End-to-end funnel |
| `docs/PHASE6_ARCHITECTURE.md` | This document |

### Extend (carefully)

| Path | Change |
|------|--------|
| `storage/registry.py` | `campaign_id`, append-only events; trial scope |
| `research/runner.py` | Honor cost/slippage model ids from config; campaign hooks |
| `research/robustness.py` | Policy id / expanded cases if missing |
| `research/scoring.py` | Keep v1; optional v2 only if approved |
| `ai/pipeline.py` | Callable from campaign stages; still no TEST |
| `ai/genealogy.py` | Ensure `campaign_id` in metadata |
| `Makefile` / `README.md` | `phase6-demo` |

### Do not create

- Parallel backtester / second eligibility checker / second StrategySpec
- Genetic algorithm package
- Broker adapters

---

## 22. Test plan (≥40)

| Area | Tests |
|------|--------|
| Campaign | Config hash stability; immutability after RUNNING; duplicate campaign_id; purpose gates |
| Generation | Budget enforcement; dedupe; genealogy fields; mock path |
| Screening | Deterministic; no TEST bars accessed; threshold versioning |
| Research | Correct dataset/splits; baseline comparison present |
| Multiple testing | Counters increment; no reset; family vs campaign; DSR uses inflated n_trials |
| Sealed TEST | Legal transitions; contamination; param immutability; double-TEST denied |
| Robustness | Child experiments linked; reproducible |
| Acceptance | Hard gates; score cannot override; DEVELOPMENT_ONLY → accepted=0 |
| Security | Spec sandbox unchanged |
| Reports | Counts complete; blockers; reproducibility hash |
| Recovery | Resume same hash; abort on dataset change |

---

## 23. Implementation order (after approval only)

1. `ResearchCampaignConfig` + immutable hashing  
2. Candidate pool + genealogy/`campaign_id`  
3. Search-space + budgets  
4. Cheap screening  
5. Campaign + candidate state machines  
6. Sealed TEST integration (`test_seal.py`)  
7. Multiple-testing campaign ledger  
8. `CampaignRunner`  
9. Reports  
10. ≥40 tests  
11. `make phase6-demo`  

---

## 24. Phase 6 demo contract

```
make phase6-demo
```

Uses existing synthetic / Phase 3.5–5 development dataset only.

Expected:

```
Campaign execution: SUCCESS
Research eligibility: DEVELOPMENT_ONLY
Accepted strategies: 0
Final research claims: NONE
```

Banner: infrastructure validation only — not evidence of edge.

---

## 25. Risks

| Risk | Mitigation |
|------|------------|
| Pressure to accept on synthetic | Hard purpose + eligibility gates; demo asserts accepted=0 |
| Trial undercounting | Campaign ledger + DSR policy; tests for no reset |
| TEST leakage via screening | Explicit bar-access guards in tests |
| Registry overwrite hides failures | Append-only events; no delete |
| Cost model config ignored | Wire models or fail if unsupported id |
| Scope creep into genetic search / LLM | Explicit non-goals |
| Score gaming | Hard rejects dominate score |

---

## 26. Approval decisions required

Before implementation, please decide:

| ID | Decision | Recommendation |
|----|----------|----------------|
| **C1** | Campaign purposes allowed in v1 | `exploratory_development` + `research` only |
| **C2** | Wire cost/slippage from ExperimentConfig in runner? | **Yes** — fail on unknown model id |
| **C3** | Registry: append-only events + stop REPLACE for finalized rows? | **Yes** for campaign-scoped rows |
| **C4** | Screening defaults (`min_trades`, DD ceiling, …) | Approve `screening_policy_v1` numbers in impl PR |
| **C5** | Walk-forward required for acceptance or optional? | Optional but if enabled, floors apply |
| **C6** | Keep `score_policy_v1` only for Phase 6? | **Yes** — no v2 unless separate approval |
| **C7** | Max demo budgets (candidates / experiments) | e.g. 20 candidates / 40 experiments |
| **C8** | Human-authored Spec path in demo? | Optional; mock sufficient for infra demo |

---

## 27. Stop conditions

This document is design only. Do not implement until explicit approval of Phase 6 (and C1–C8 as needed).

Do not: connect LLM, add brokers/paper/live, add genetic search, weaken Phase 5 gates, or manufacture `RESEARCH_ELIGIBLE` data.
