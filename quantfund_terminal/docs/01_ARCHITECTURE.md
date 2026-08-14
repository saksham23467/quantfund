# QuantFund Research Terminal — Architecture

> Bloomberg Terminal × QuantConnect Research × institutional backtesting, focused
> on Indian markets — built on a **certification-first, fail-closed** data core.

## 1. Design principles

1. **Certification is the product, not a feature.** No strategy is ever
   *accepted* on data that is not `RESEARCH_ELIGIBLE`. The product layer *reads*
   the verdict from the unmodified `ResearchEligibilityChecker`; it can never
   promote a dataset or weaken a gate.
2. **Read-only demo posture.** The terminal places no orders and holds no
   broker-write capability. `live_trading=DISABLED`, `paper_trading=NOT_STARTED`,
   `kill_switch=ARMED` are surfaced on every screen.
3. **Provenance on every number.** Every panel carries a `data_class`
   (`RESEARCH_ELIGIBLE` / `DEVELOPMENT_DATA` / `DEMO_SYNTHETIC`) and a source
   label. Illustrative results are labelled illustrative.
4. **Reproducibility.** Every backtest is bound to a dataset content hash and an
   experiment hash; certification is deterministic.
5. **Thin product over a hardened core.** The existing `quantfund` research
   package is a dependency, not a fork.

## 2. System context (C4 level 1)

```
        ┌──────────────┐         ┌───────────────────────────────┐
Investor│              │  HTTPS  │  Next.js Frontend (Terminal)   │
Analyst ├─ browser ───►│         │  10 feature panels, dark UI    │
Quant PM│              │         └───────────────┬───────────────┘
        └──────────────┘                         │ REST/JSON (read-mostly)
                                                  ▼
                                  ┌───────────────────────────────┐
                                  │  research_api (FastAPI)        │
                                  │  gateway + auth + rate limit   │
                                  └───┬───────────┬───────────┬────┘
                                      │           │           │
                     ┌────────────────┘     ┌─────┘      ┌────┘
                     ▼                      ▼            ▼
        ┌────────────────────┐  ┌────────────────┐  ┌──────────────────┐
        │ analytics_engine   │  │ copilot        │  │ quantfund (core) │
        │ metrics/backtest/  │  │ intent router  │  │ certification /  │
        │ factors/portfolio/ │  │ NL→SQL+workflow│  │ PIT / eligibility│
        │ risk (pure python) │  └────────────────┘  │ (UNMODIFIED)     │
        └─────────┬──────────┘                      └────────┬─────────┘
                  │                                          │
                  ▼                                          ▼
        ┌────────────────────┐                    ┌────────────────────┐
        │ Postgres (research │                    │ Immutable certified │
        │ metadata, results, │                    │ data packages on    │
        │ audit, users)      │                    │ object store (S3)   │
        └────────────────────┘                    └────────────────────┘
                  ▲
                  │
        ┌────────────────────┐
        │ Redis (cache,      │
        │ market snapshot,   │
        │ job queue, rate    │
        │ limiting)          │
        └────────────────────┘
```

## 3. Components

| Component | Tech | Responsibility | Trading capability |
|---|---|---|---|
| `frontend/` | Next.js 14 (App Router), TypeScript | Terminal UI, 10 panels, provenance/safety badges | none |
| `backend/` (`research_api`) | FastAPI, Pydantic v2 | API gateway, auth, rate limiting, response contracts | **none (read-only)** |
| `analytics_engine/` | Python, numpy, pandas | Metrics, vectorized backtests (next-bar), factors, portfolio & risk analytics | none |
| `copilot/` | Python | Deterministic NL→plan (SQL + workflow); LLM pluggable behind same contract | none |
| `quantfund` (core) | Python | Dataset certification, PIT universe, eligibility, leakage/reproducibility gates | none (gated) |
| Postgres | 16 | Users, strategies, backtests, factor scores, datasets, certifications, audit log | — |
| Redis | 7 | Market-snapshot cache, backtest job queue, rate limits, sessions | — |
| Object store | S3-compatible | Immutable certified data packages (`manifest/checksums/provenance/certification`) | — |

## 4. Request lifecycle (backtest example)

1. UI `POST /api/backtest` with universe/date-range/costs/slippage.
2. Gateway loads the selected dataset's **certification verdict** first.
3. `analytics_engine.run_backtest` executes vectorized, next-bar, cost/slippage-aware.
4. Metrics computed (CAGR/Sharpe/Sortino/MaxDD/Win/PF/Turnover/Exposure).
5. Result annotated with `data_class`, `verdict`, `dataset_hash`, `experiment_hash`.
6. Persisted to Postgres `backtests`; append-only row in `audit_log`.
7. If dataset is not `RESEARCH_ELIGIBLE`, response carries an *illustrative* banner;
   the result can never be `ACCEPTED` on the leaderboard.

## 5. Data classes and the "moat" flow

```
RAW broker/dev data ──► ingestion (hash, dedup, coverage) ──► certification engine
                                                              │
                    ┌─────────────────────────────────────────┤
                    ▼                                          ▼
          RESEARCH_ELIGIBLE                             DEVELOPMENT_ONLY
      (authoritative source + PIT + ISIN            (fail closed; usable for
       + delisting + calendar + CA, all             engineering/plumbing only;
       reproducible & immutable)                    never accepted for research)
```

Today the repo's certified verdict is **`DEVELOPMENT_ONLY`** (non-exchange
source, no PIT/ISIN/delisting/calendar/CA ledgers). The terminal shows exactly
this — honestly — and explains to investors what unlocking `RESEARCH_ELIGIBLE`
requires. That honesty *is* the differentiator.

## 6. Security & tenancy (production)

- OAuth2/OIDC (e.g. Auth0/Cognito) → JWT; RBAC roles: `viewer`, `analyst`, `pm`, `admin`.
- Row-level tenant isolation in Postgres (`org_id`).
- All mutating endpoints audited; the gateway has **no** broker credentials.
- Secrets via env/secrets manager; TLS everywhere; CORS locked to app origins.

## 7. Scalability path

- Stateless gateway behind a load balancer; horizontal scale.
- Heavy backtests move from inline to a Redis/RQ (or Celery) worker pool; UI polls a job id.
- Market data fan-out via a websocket service (Feature 1 real-time) once a
  licensed feed is connected — only `market_service` changes; the API contract is stable.
- Certified packages are immutable and content-addressed → trivially cacheable/CDN-able.

## 8. Deployment

- Frontend: Vercel (or containerized Next standalone).
- Backend + workers: containers on ECS/Fly/Render; Postgres (RDS/Neon); Redis (Elasticache/Upstash).
- CI: run `quantfund` gate tests + gateway smoke test + frontend typecheck on every PR.
