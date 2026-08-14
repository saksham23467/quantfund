# Database Schema

Postgres 16 is the system of record for research metadata, results, and the
audit trail. Redis is a cache / queue / rate-limiter (not a source of truth).
Certified data packages themselves are **immutable, content-addressed files** on
an object store — Postgres only stores their hashes and provenance pointers.

## Conventions

- All tables have `id bigint generated always as identity primary key`.
- Multi-tenant via `org_id bigint not null references orgs(id)`.
- Timestamps `timestamptz default now()`; append-only tables never `UPDATE`.
- Money/ratios stored as `numeric` (never float) where correctness matters.

## DDL

```sql
-- Tenancy & identity ---------------------------------------------------------
create table orgs (
  id            bigint generated always as identity primary key,
  name          text not null,
  plan          text not null default 'trial',   -- trial|analyst|team|enterprise
  created_at    timestamptz not null default now()
);

create table users (
  id            bigint generated always as identity primary key,
  org_id        bigint not null references orgs(id),
  email         citext not null unique,
  role          text not null default 'analyst',  -- viewer|analyst|pm|admin
  created_at    timestamptz not null default now()
);

-- Datasets & certification (the moat) ----------------------------------------
create table datasets (
  id                bigint generated always as identity primary key,
  org_id            bigint references orgs(id),
  dataset_id        text not null,             -- logical id, e.g. nse_eq_daily
  dataset_version   text not null,             -- semver-ish
  source_name       text not null,
  source_type       text not null,             -- EXCHANGE|LICENSED|BROKER|PUBLIC
  source_grade      text not null,             -- exchange|research|non_exchange
  data_class        text not null,             -- RESEARCH_DATA|DEVELOPMENT_DATA|DEMO_SYNTHETIC
  coverage_start    date,
  coverage_end      date,
  content_hash      text not null,             -- sha256 of the immutable package
  object_uri        text,                      -- s3://.../v{n}/
  immutable         boolean not null default true,
  created_at        timestamptz not null default now(),
  unique (dataset_id, dataset_version)
);

create table certifications (
  id                            bigint generated always as identity primary key,
  dataset_id                    bigint not null references datasets(id),
  verdict                       text not null,   -- RESEARCH_ELIGIBLE|DEVELOPMENT_ONLY
  research_eligible             boolean not null,
  eligibility_level             text,
  membership_coverage_ratio     numeric,
  instrument_identity_coverage  numeric,
  delisted_coverage             text,            -- none|partial|complete|unknown
  corporate_action_coverage     text,
  calendar_verified             boolean,
  calendar_errors               integer,
  leakage_safe                  boolean,
  reproducible                  boolean,
  immutable                     boolean,
  blockers                      jsonb not null default '[]',
  capability_gaps               jsonb not null default '[]',
  generated_at                  timestamptz not null default now()
);
create index on certifications (dataset_id, generated_at desc);

-- PIT universe & security identity -------------------------------------------
create table universe_membership (
  id            bigint generated always as identity primary key,
  dataset_id    bigint not null references datasets(id),
  universe_id   text not null,                 -- e.g. NIFTY50
  symbol        text not null,
  isin          text,
  member_from   date not null,
  member_to     date,                          -- null = still a member
  source        text not null
);
create index on universe_membership (universe_id, symbol, member_from);

create table security_master (
  id            bigint generated always as identity primary key,
  dataset_id    bigint not null references datasets(id),
  isin          text not null,
  exchange      text not null,
  instrument_id text not null,
  symbol        text not null,
  valid_from    date not null,
  valid_to      date,
  source        text not null
);

-- Strategies, backtests, factors ---------------------------------------------
create table strategies (
  id            bigint generated always as identity primary key,
  org_id        bigint not null references orgs(id),
  name          text not null,
  family        text not null,                 -- momentum|trend|mean_reversion|breakout|volatility
  params        jsonb not null default '{}',
  status        text not null default 'DRAFT', -- DRAFT|BACKTESTED|ACCEPTED|REJECTED|RESEARCH_ONLY
  created_by    bigint references users(id),
  created_at    timestamptz not null default now()
);

create table backtests (
  id                bigint generated always as identity primary key,
  strategy_id       bigint not null references strategies(id),
  dataset_id        bigint not null references datasets(id),
  start             date,
  "end"             date,
  cost_bps          numeric not null,
  slippage_bps      numeric not null,
  cagr              numeric,
  sharpe            numeric,
  sortino           numeric,
  max_drawdown      numeric,
  win_rate          numeric,
  profit_factor     numeric,
  turnover          numeric,
  exposure          numeric,
  dsr               numeric,                    -- deflated sharpe ratio (core gate)
  data_class        text not null,              -- inherited from dataset
  dataset_hash      text not null,
  experiment_hash   text not null,              -- reproducibility key
  created_at        timestamptz not null default now()
);
create index on backtests (strategy_id, created_at desc);

create table factor_scores (
  id            bigint generated always as identity primary key,
  dataset_id    bigint not null references datasets(id),
  factor        text not null,                 -- momentum|quality|value|low_vol|size
  symbol        text not null,
  score         numeric not null,
  is_proxy      boolean not null default false,
  as_of         date not null
);
create index on factor_scores (factor, as_of);

-- Leaderboard is a view over accepted/evaluated backtests --------------------
create view strategy_leaderboard as
select s.name as strategy, s.family,
       b.cagr, b.sharpe, b.max_drawdown, b.dsr,
       case
         when s.status = 'ACCEPTED' then 'ACCEPTED'
         when s.status = 'REJECTED' then 'REJECTED'
         else 'RESEARCH_ONLY'
       end as status
from strategies s
join lateral (
  select * from backtests bt where bt.strategy_id = s.id
  order by bt.created_at desc limit 1
) b on true;

-- Institutional audit trail (append-only) ------------------------------------
create table audit_log (
  id            bigint generated always as identity primary key,
  org_id        bigint references orgs(id),
  actor         text,                          -- user email | 'copilot' | 'system'
  action        text not null,                 -- CREATE_STRATEGY|RUN_BACKTEST|VIEW_CERT|...
  entity_type   text,
  entity_id     bigint,
  dataset_hash  text,
  experiment_hash text,
  metadata      jsonb not null default '{}',
  created_at    timestamptz not null default now()
);
create index on audit_log (org_id, created_at desc);
```

## Redis keyspace

| Key pattern | Type | TTL | Purpose |
|---|---|---|---|
| `market:snapshot:{universe}` | string(json) | 15s (live) / 1d (delayed) | Feature 1 cache |
| `backtest:job:{id}` | hash | 1h | async backtest status/result pointer |
| `rate:{user}:{window}` | counter | window | API rate limiting |
| `session:{token}` | string | session | auth session cache |
| `factors:{dataset}:{lookback}` | string(json) | 6h | factor panel cache |

## Immutability guarantees

- A dataset row is **insert-once**; any change requires a new `dataset_version`
  and a new `content_hash` (enforced by `unique(dataset_id, dataset_version)`).
- `certifications`, `backtests`, and `audit_log` are append-only by policy.
- The certified package files carry `manifest.json`, `checksums.json`,
  `provenance.json`, `certification.json` and are verified against `content_hash`
  before use (see `quantfund.research.certification.immutability`).
