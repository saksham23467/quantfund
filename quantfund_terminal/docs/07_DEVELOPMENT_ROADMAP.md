# Development Roadmap

Financing-aligned. Each stage ends at a milestone an investor can verify and a
technical state that de-risks the next round. Trading remains disabled until an
explicit, separately-funded, compliance-gated stage — never a default.

## Stage 0 — Now (this repo)
- Certification-first core (`ResearchEligibilityChecker`, PIT, leakage,
  reproducibility, immutability) — **done, unmodified**.
- Investor-demo product layer: read-only gateway + 10-panel terminal +
  analytics engine + copilot — **done (this deliverable)**.
- Honest verdict: `DEVELOPMENT_ONLY`. Safety: all trading DISABLED.

## Pre-seed ($500k) — "Prove the moat + one real dataset" · ~6 months
**Goal:** one genuinely `RESEARCH_ELIGIBLE` dataset end-to-end; 5–10 design partners.
- Sign one licensed/authoritative NSE-equities source (see repo's source-options work).
- Implement the corresponding `ResearchDataProvider` adapters (bars, security
  master/ISIN, PIT membership, delisting, calendar, corporate actions).
- Ingest → certify → flip a real dataset to `RESEARCH_ELIGIBLE` (no gate changes).
- Persist to Postgres; wire the terminal off Postgres instead of report files.
- AuthN/AuthZ (OIDC + RBAC), multi-tenant `org_id`, audit log persisted.
- Replace synthetic market panel with a delayed licensed feed.
- **Milestones:** 1 certified dataset; leaderboard populated with reproducible,
  DSR-passing research strategies; 5 design partners running weekly research.

## Seed ($2M) — "Product-led research platform" · ~12–18 months
**Goal:** self-serve institutional research SaaS; $300k–$600k ARR.
- Async backtest workers (Redis/RQ), job queue, larger universes (NIFTY 200/500).
- Real-time market data via websockets (Feature 1 live tier).
- Copilot: plug a hosted LLM behind the deterministic `plan()` contract; keep the
  SQL/workflow auditable and certification-gated.
- Full factor library with certified fundamentals (Quality/Value real, not proxy).
- Point-in-time fundamentals + alternative datasets, each independently certified.
- Team features: shared workspaces, strategy versioning, report export (PDF).
- SOC 2 Type I; India data-residency posture.
- **Milestones:** 25–40 paying orgs; net revenue retention > 110%; certified data
  catalog of 5+ datasets across asset classes.

## Series A ($10M) — "Institutional standard for Indian quant research" · 18–30 months
**Goal:** category leadership; $3M+ ARR; multi-asset, multi-market.
- Extend to F&O, fixed income, and additional exchanges; each with its own
  certification lineage.
- Data marketplace: third parties publish **certified** datasets; revenue share.
- Managed research environments (notebooks) that can *only* read certified data.
- Optional, compliance-gated **paper-trading** module (still no live by default),
  behind explicit legal review, kill-switch, and per-tenant opt-in.
- Enterprise: SSO/SAML, VPC deploy, audit exports, SOC 2 Type II.
- **Milestones:** 100+ orgs incl. AMCs/PMS/family offices; reference customers;
  defensible certified-data catalog as the durable moat.

## Explicitly out of scope (until a dedicated, compliance-led initiative)
- Autonomous/live trading, broker-write capability, auto-graduation to live.
- Any weakening of eligibility, DSR, PIT, leakage, reproducibility, or
  broker-write gates. These remain hard invariants at every stage.

## Engineering guardrails (every stage)
- CI runs the core gate tests + gateway smoke test + frontend typecheck on each PR.
- No product code path can mutate a certification verdict or place an order.
- Every research result is content-hash bound and reproducible.
