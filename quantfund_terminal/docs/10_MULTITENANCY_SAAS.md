# Multi-Tenant SaaS Architecture (v2)

v2 turns the read-only terminal into a multi-tenant research SaaS **without
touching QuantFund Core**. The core (certification, eligibility, PIT, DSR,
leakage, reproducibility, safety) is consumed strictly as an authoritative,
read-only source of verdicts.

## Tenancy model

- **Org** (tenant) → has **Users** (roles) and one **Subscription**.
- Every business row carries `org_id`. Shared research assets — the **dataset
  catalog** and their **certifications** — are global (a certified dataset is a
  company-wide asset, licensed per plan).
- Isolation: application-level `org_id` scoping today; production adds Postgres
  Row-Level Security (RLS) policies keyed on a `SET app.current_org` GUC.

## RBAC

| Role | Rank | Can |
|---|---|---|
| `viewer` | 0 | read dashboards, marketplace, certification, audit |
| `analyst` | 1 | + create strategy drafts, run backtests, studio, copilot |
| `pm` | 2 | + publish to marketplace, view org users |
| `admin` | 3 | + manage orgs, billing checkout |

Enforced by the `require_role(min_role)` dependency (`backend/app/auth.py`).
The v2 smoke test asserts a `viewer` is `403` on admin/pm routes.

### Auth in demo vs production
- **Demo:** identity is passed via `X-Org-Slug` / `X-User-Email` / `X-Role`
  headers (the UI's persona switcher). Zero infra, fully reproducible.
- **Production:** an OIDC/JWT (Auth0/Cognito) is verified at the edge; the same
  `get_context` dependency reads verified claims. **Router code does not change.**

## Data stores

| Store | Local/demo | Production | Purpose |
|---|---|---|---|
| Relational | SQLite file | RDS Postgres 16 | orgs/users/subs/datasets/certifications/strategies/backtests/records/audit |
| Cache/queue | in-process | ElastiCache Redis 7 | market snapshot, backtest jobs, rate limits, sessions |
| Object store | local path | S3 (Object Lock/WORM) | immutable certified data packages |

`QFT_DATABASE_URL` and `QFT_REDIS_URL` switch environments; absent Redis falls
back to an in-process cache (`util/cache.py`). Nothing *requires* external infra
to run the demo.

## Subscriptions & billing

- Plans: `analyst` / `team` / `enterprise` (`billing/provider.py:PLAN_CATALOG`).
- Billing is behind a `BillingProvider` interface. Default is `MockBillingProvider`
  (no secrets, no charges). Set `QFT_BILLING_PROVIDER=stripe` +
  `QFT_STRIPE_WEBHOOK_SECRET` to enable a real provider implementing the same
  interface. Webhook endpoint: `POST /api/v2/billing/webhook`.
- SaaS metrics (MRR/ARR/seats/ARPA) on the Investor Dashboard are computed live
  from subscription rows.

## Immutable research records (reproducibility proofs)

- `research_records` is an **append-only, hash-linked chain**: each record's
  `content_hash = sha256(canonical_json(kind, ref_id, payload, prev_hash))`.
- Any tampering breaks the chain; `GET /api/v2/audit/verify` recomputes it and
  reports the first break (the v2 smoke test asserts `intact=true`).
- Every marketplace publish and copilot query appends a record + an `audit_log`
  entry. Backtests store `dataset_hash` + `experiment_hash`; the marketplace
  `.../proof` endpoint **re-runs** the exact config and checks metrics match.

## What v2 explicitly does NOT change

- No modification to `ResearchEligibilityChecker`, DSR/PIT/leakage/reproducibility
  gates, or broker-write guards.
- No order placement, paper/live trading, or auto-promotion.
- Certification verdicts are read-only; the product can never promote a dataset.
  The dataset exchange shows `research_eligible_count = 0` today, honestly.

## Request path (v2)

```
Browser (persona headers / prod: JWT)
   → CloudFront → ALB → ECS(frontend Next standalone)
   → ALB → ECS(backend FastAPI)
        → get_context (tenant + RBAC)
        → service (analytics_engine / quantfund core read-only)
        → Postgres (RLS by org) + Redis (cache) + S3 (packages)
        → append immutable research record + audit_log
```
