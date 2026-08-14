"""Investor Dashboard — TAM, SaaS metrics, dataset moat, competitive comparison.

SaaS metrics are computed from live subscription rows; TAM and competitive rows
are clearly-labelled estimates (not audited market data).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.db.models import (
    Certification,
    Dataset,
    Org,
    Subscription,
)

# Illustrative TAM (top-down), labelled as estimates for the pitch.
TAM = {
    "currency": "USD",
    "segments": [
        {"name": "Global market/analytics data (SAM anchor)", "size": 38_000_000_000,
         "basis": "market-data & analytics industry, est."},
        {"name": "India institutional research & data (SAM)", "size": 900_000_000,
         "basis": "AMCs/PMS/AIFs/family offices/brokers research spend, est."},
        {"name": "Serviceable Obtainable (SOM, 3-5 yr)", "size": 60_000_000,
         "basis": "certified-data + research SaaS wedge, est."},
    ],
    "disclaimer": "Top-down estimates for illustration; not audited third-party figures.",
}

COMPETITORS = [
    {"name": "Bloomberg Terminal", "india_depth": "broad", "certification_gate": False,
     "reproducibility": False, "no_code_research": "limited", "approx_cost": "~$24k+/seat/yr",
     "our_edge": "India-native, certification-first, reproducible, fraction of cost"},
    {"name": "FactSet", "india_depth": "broad", "certification_gate": False,
     "reproducibility": False, "no_code_research": "limited", "approx_cost": "~$12k+/yr",
     "our_edge": "trust-as-a-feature + India quant depth"},
    {"name": "Refinitiv / LSEG", "india_depth": "broad", "certification_gate": False,
     "reproducibility": False, "no_code_research": "limited", "approx_cost": "~$12-22k/yr",
     "our_edge": "fail-closed eligibility vs assumed-good data"},
    {"name": "QuantConnect", "india_depth": "limited", "certification_gate": False,
     "reproducibility": "partial", "no_code_research": "code-first", "approx_cost": "$/mo tiers",
     "our_edge": "certified Indian PIT data + no-code analyst UX"},
    {"name": "TradingView", "india_depth": "charts", "certification_gate": False,
     "reproducibility": False, "no_code_research": "pine-script", "approx_cost": "$/mo tiers",
     "our_edge": "diligence-grade research vs retail charting"},
]


def investor_dashboard(db: Session) -> dict:
    subs = db.execute(select(Subscription).where(Subscription.status.in_(["active", "trialing"]))).scalars().all()
    mrr = sum(s.mrr_inr for s in subs)
    seats = sum(s.seats for s in subs)
    orgs = db.execute(select(func.count(Org.id))).scalar() or 0

    by_plan: dict[str, dict] = {}
    for s in subs:
        b = by_plan.setdefault(s.plan, {"orgs": 0, "seats": 0, "mrr_inr": 0.0})
        b["orgs"] += 1
        b["seats"] += s.seats
        b["mrr_inr"] += s.mrr_inr

    n_datasets = db.execute(select(func.count(Dataset.id))).scalar() or 0
    n_eligible = db.execute(
        select(func.count(Certification.id)).where(Certification.research_eligible.is_(True))
    ).scalar() or 0

    return {
        "saas_metrics": {
            "orgs": orgs,
            "active_subscriptions": len(subs),
            "seats": seats,
            "mrr_inr": round(mrr, 2),
            "arr_inr": round(mrr * 12, 2),
            "arpa_inr": round(mrr / len(subs), 2) if subs else 0.0,
            "by_plan": by_plan,
        },
        "dataset_moat": {
            "datasets_in_catalog": n_datasets,
            "research_eligible": n_eligible,
            "development_only": n_datasets - n_eligible,
            "why_moat": (
                "Each certified dataset is an immutable, versioned, provenance-tracked "
                "asset. The catalog compounds and is expensive to replicate (licensing "
                "+ engineering + provenance rigor)."
            ),
        },
        "tam": TAM,
        "competitive_comparison": COMPETITORS,
        "traction_note": (
            "Figures reflect seeded demo tenants. Pre-seed milestone: one genuinely "
            "RESEARCH_ELIGIBLE dataset + 5-10 design partners."
        ),
    }
