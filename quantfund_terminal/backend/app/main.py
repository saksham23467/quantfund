"""QuantFund Research Terminal — FastAPI gateway (research_api).

Read-only institutional research API. It surfaces the certified QuantFund
infrastructure and analytics engine; it enables no paper/live trading and holds
no broker-write capability.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from quantfund_terminal.backend.app.config import CORS_ALLOW_ORIGINS, SAFETY_STATE
from quantfund_terminal.backend.app.db import init_db
from quantfund_terminal.backend.app.routers import (
    audit_v2,
    backtest,
    billing,
    copilot,
    copilot_v2,
    exchange,
    factors,
    investor,
    market,
    marketplace,
    moat,
    portfolio,
    research,
    risk,
    studio,
    tenancy,
)
from quantfund_terminal.backend.app.util.cache import cache_backend

app = FastAPI(
    title="QuantFund Research Terminal API",
    version="0.1.0",
    description=(
        "Institutional research terminal for Indian markets. Read-only; "
        "certification-gated; no paper/live trading."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# v1 (read-only research terminal)
for r in (market, research, backtest, factors, portfolio, risk, copilot, moat):
    app.include_router(r.router)

# v2 (multi-tenant SaaS: exchange, marketplace, studio, investor, billing, audit)
for r in (
    tenancy,
    exchange,
    marketplace,
    studio,
    copilot_v2,
    investor,
    billing,
    audit_v2,
):
    app.include_router(r.router)


@app.on_event("startup")
def _startup() -> None:
    # Create tables if absent (SQLite locally / Postgres in prod). Never drops.
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "safety_state": SAFETY_STATE, "cache_backend": cache_backend()}


@app.get("/api/safety")
def safety() -> dict:
    return SAFETY_STATE
