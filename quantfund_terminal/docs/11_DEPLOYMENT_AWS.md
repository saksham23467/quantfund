# AWS Production Deployment

Target: a secure, multi-tenant SaaS on AWS in **ap-south-1 (Mumbai)** for India
data residency. Managed services only; no self-managed databases.

## Topology

```
                        ┌──────────────────────────────────────────┐
             Route 53   │                CloudFront                 │
  users ───► DNS ──────►│  (frontend static/SSR cache, TLS, WAF)    │
                        └───────────────┬───────────────┬───────────┘
                                        │               │  /api/* (behavior)
                       (frontend origin)│               │
                                        ▼               ▼
                              ┌───────────────┐  ┌───────────────┐
                              │  ALB (public) │  │  ALB (public) │
                              └───────┬───────┘  └───────┬───────┘
                                      ▼                  ▼
                          ECS/Fargate: frontend   ECS/Fargate: backend
                          (Next standalone :3000)  (FastAPI :8000, N tasks)
                                                        │
                     ┌──────────────────────────────────┼───────────────────┐
                     ▼                    ▼              ▼                    ▼
              RDS Postgres 16      ElastiCache Redis   S3 (Object Lock)   Secrets Manager
              (Multi-AZ, private)  (private)           certified packages  DB/JWT/Stripe
                     ▲
                     │  backtest workers (ECS service, Redis/RQ queue)
                     └── ECS/Fargate: worker (async backtests, larger universes)
```

## Components

| Concern | Service | Notes |
|---|---|---|
| Frontend | ECS/Fargate (Next standalone) or S3+CloudFront (if fully static) | image from `frontend/Dockerfile` |
| Backend API | ECS/Fargate service behind ALB | image from `backend/Dockerfile` (context = repo root) |
| Async backtests | ECS/Fargate worker + Redis queue | scale independently from API |
| Relational | RDS Postgres 16, Multi-AZ, encrypted | `QFT_DATABASE_URL` via Secrets Manager |
| Cache/queue | ElastiCache Redis 7, encrypted in-transit/at-rest | `QFT_REDIS_URL` |
| Object store | S3 with **Object Lock (WORM)** + versioning | immutable certified packages |
| CDN/TLS/WAF | CloudFront + ACM + AWS WAF | rate limiting, geo rules |
| Identity | Cognito (or Auth0) → JWT | verified at ALB/edge; claims → `get_context` |
| Secrets | Secrets Manager / SSM | DB creds, Stripe secret, JWT signing |
| Registry | ECR | backend + frontend images |
| Observability | CloudWatch + OpenTelemetry | logs, metrics, traces; Container Insights |
| IaC | Terraform (`infra/terraform/`) | skeleton provided; fill VPC/IAM/ALB/ECS |

## Build & push images

```bash
# Backend (context MUST be repo root)
docker build -f quantfund_terminal/backend/Dockerfile -t $ECR/quantfund-backend:$(git rev-parse --short HEAD) .
# Frontend
docker build -f quantfund_terminal/frontend/Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE=https://api.quantfund.example \
  -t $ECR/quantfund-frontend:$(git rev-parse --short HEAD) quantfund_terminal/frontend
docker push $ECR/quantfund-backend:...   && docker push $ECR/quantfund-frontend:...
```

## Environment (backend task)

| Var | Example | Purpose |
|---|---|---|
| `QFT_DATABASE_URL` | `postgresql+psycopg://user:***@rds:5432/quantfund` | RDS |
| `QFT_REDIS_URL` | `rediss://elasticache:6379/0` | ElastiCache (TLS) |
| `QFT_BILLING_PROVIDER` | `stripe` | billing |
| `QFT_STRIPE_WEBHOOK_SECRET` | `whsec_***` | webhook verification |

DB schema is created idempotently on startup (`init_db`); for controlled
migrations add Alembic and run as an ECS one-off task in the deploy pipeline.

## Security & compliance

- Private subnets for RDS/ElastiCache; SGs restrict to the backend service only.
- S3 Object Lock enforces immutability of certified packages (matches the
  core's immutability guarantee); versioning keeps every dataset version.
- WAF on CloudFront; TLS everywhere (ACM); least-privilege IAM task roles.
- Audit log + hash-linked research records give allocator-grade traceability.
- **No broker credentials anywhere in this stack** — the platform is read-only
  with respect to trading by design.

## Scaling

- Backend API: horizontal (stateless) behind ALB target-tracking autoscaling.
- Backtests: move off the request path to the worker service (Redis/RQ); the UI
  polls a job id. Larger universes (NIFTY 200/500) scale the worker pool only.
- Certified packages are content-addressed and immutable → aggressively cacheable
  via CloudFront/S3.

## Rollout

1. `terraform apply` (per env) to provision RDS/Redis/S3/ECS/ALB/CloudFront.
2. CI builds + pushes images to ECR; updates ECS services (blue/green via
   CodeDeploy).
3. Run DB migration task; smoke-test `/health` and `/api/v2/audit/verify`.
4. Flip CloudFront/Route53 to the new version.
```
