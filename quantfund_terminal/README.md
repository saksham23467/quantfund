# QuantFund Research Terminal

> Bloomberg-style research terminal × QuantConnect research × institutional
> backtesting — for Indian markets, built on a **certification-first,
> fail-closed** data core.

This is the first **investor-demo product** layered on top of the existing,
unmodified QuantFund research infrastructure (dataset certification, PIT universe,
survivorship protection, eligibility/DSR/leakage/reproducibility gates, audit
trail). It is **read-only**: it places no orders, holds no broker-write
capability, and enables no paper/live trading. Every screen surfaces the safety
posture (`live_trading=DISABLED`, `kill_switch=ARMED`) and each dataset's
provenance verdict (`RESEARCH_ELIGIBLE` / `DEVELOPMENT_ONLY` / `DEMO_SYNTHETIC`).

## Features

**Research (v1):** 1. Market Dashboard · 2. Research Lab · 3. Backtest Engine ·
4. Factor Research · 5. Portfolio Analytics · 6. Risk Command Center ·
7. AI Research Copilot.

**Platform (v2, multi-tenant SaaS):** Dataset Certification (the moat) ·
Research Dataset Exchange · Strategy Marketplace (leaderboard + reproducibility
proofs) · Portfolio Analytics Studio (factor attribution, risk decomposition,
scenario analysis) · Audit Trail (immutable hash-linked records) · Investor
Dashboard (TAM, SaaS metrics, dataset moat, competitive comparison).

v2 adds multi-tenancy (orgs/users), RBAC (viewer/analyst/pm/admin), subscriptions
+ billing hooks, PostgreSQL (SQLite locally), Redis (in-process fallback), and an
append-only reproducibility ledger — all **without modifying QuantFund Core**,
which is consumed read-only as an authoritative source of verdicts.

## Architecture (at a glance)

```
frontend/ (Next.js + TS)  →  backend/ research_api (FastAPI, read-only)
                                 ├── analytics_engine/  (metrics, backtest, factors, portfolio, risk)
                                 ├── copilot/           (deterministic NL → SQL + workflow plan)
                                 └── quantfund core      (certification / PIT / eligibility — UNMODIFIED)
Postgres (metadata/results/audit) · Redis (cache/queue/rate-limit) · S3 (immutable certified packages)
```

Full design docs live in [`docs/`](docs/):
`01_ARCHITECTURE` · `02_FOLDER_STRUCTURE` · `03_DATABASE_SCHEMA` ·
`04_API_CONTRACTS` · `05_UI_WIREFRAMES` · `06_INVESTOR_DEMO_FLOW` ·
`07_DEVELOPMENT_ROADMAP` · `08_REVENUE_MODEL` · `09_COMPETITIVE_COMPARISON` ·
`10_MULTITENANCY_SAAS` · `11_DEPLOYMENT_AWS`.

## Run it

### 1. Backend (API gateway on :8000)
Uses the repository's existing `.venv` (already provides `quantfund`, `numpy`,
`pandas`). The script installs `fastapi`/`uvicorn`/`sqlalchemy` on first run and
seeds demo data (idempotent).
```bash
quantfund_terminal/backend/run.sh
# → http://localhost:8000   (OpenAPI docs at /docs)
```

Seed manually / reset the demo database:
```bash
.venv/bin/python quantfund_terminal/backend/seed.py           # idempotent
.venv/bin/python quantfund_terminal/backend/seed.py --reset   # rebuild
```

Smoke-test everything (v1 read-only + v2 SaaS) against the real reports:
```bash
.venv/bin/python quantfund_terminal/backend/smoke_test.py     # v1
.venv/bin/python quantfund_terminal/backend/smoke_test_v2.py  # v2 (RBAC, proofs, chain)
```

### Or run the full stack with Docker (Postgres + Redis + API + UI)
```bash
cd quantfund_terminal && docker compose up --build
# frontend :3000 · backend :8000 · postgres :5432 · redis :6379
```

### 2. Frontend (terminal UI on :3000)
```bash
cd quantfund_terminal/frontend
cp .env.local.example .env.local      # NEXT_PUBLIC_API_BASE=http://localhost:8000
npm install
npm run dev
# → http://localhost:3000
```

The left nav is split into **Research** and **Platform** sections, with a
**persona switcher** (org + role) at the bottom that drives RBAC — switch to a
`viewer` and admin-only actions (billing checkout, marketplace publish) correctly
refuse (`403`). Visit **Dataset Exchange**, **Strategy Marketplace** (click
_verify_ on a row for a live reproducibility proof), **Analytics Studio**,
**Audit Trail**, and **Investor Dashboard**.

## Data honesty (why the demo shows DEVELOPMENT_ONLY)

- The **moat** panels (Certification, Leaderboard, Audit) read the *real* reports
  produced by the core (`reports/research_data_certification.json`,
  `reports/phase19_strategy_search.json`). Today the honest verdict is
  **`DEVELOPMENT_ONLY`** (non-exchange source; no PIT/ISIN/delisting/calendar/CA
  ledgers), so **zero** strategies are accepted. This is by design and is the pitch.
- The **analytical** panels (Market, Backtest, Factors, Portfolio, Risk) run on a
  clearly-labelled **`DEMO_SYNTHETIC`** panel so the engine is demonstrable without
  any real/licensed data. Results are badged *illustrative* and can never be
  presented as certified alpha.
- When a licensed/authoritative dataset is connected and certified, **nothing else
  in the product changes** — the gates simply pass and the leaderboard fills.

## Invariants (never violated by this layer)

- No modification of `ResearchEligibilityChecker`, DSR/PIT/leakage/reproducibility
  gates, or broker-write guards.
- No order placement, no paper/live trading, no auto-promotion.
- Every result is reproducible and content-hash bound.
