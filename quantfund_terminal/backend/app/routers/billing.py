"""Billing hooks: plans, checkout (mock), subscription, webhook."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.auth import TenantContext, get_context, require_role
from quantfund_terminal.backend.app.billing import get_billing_provider
from quantfund_terminal.backend.app.billing.provider import PLAN_CATALOG
from quantfund_terminal.backend.app.db import get_db
from quantfund_terminal.backend.app.db.models import Subscription
from quantfund_terminal.backend.app.schemas import CheckoutRequest
from quantfund_terminal.backend.app.services.records_service import audit

router = APIRouter(prefix="/api/v2/billing", tags=["billing"])


@router.get("/plans")
def plans() -> dict:
    provider = get_billing_provider()
    return {"provider": provider.name, "plans": PLAN_CATALOG}


@router.get("/subscription")
def subscription(
    db: Session = Depends(get_db), ctx: TenantContext = Depends(get_context)
) -> dict:
    sub = None
    if ctx.org_id:
        sub = db.execute(
            select(Subscription).where(Subscription.org_id == ctx.org_id).limit(1)
        ).scalar_one_or_none()
    if not sub:
        return {"org": ctx.org_slug, "subscription": None}
    return {
        "org": ctx.org_slug,
        "subscription": {
            "plan": sub.plan,
            "status": sub.status,
            "seats": sub.seats,
            "mrr_inr": sub.mrr_inr,
            "renews_at": sub.renews_at.isoformat() if sub.renews_at else None,
        },
    }


@router.post("/checkout")
def checkout(
    req: CheckoutRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("admin")),
) -> dict:
    provider = get_billing_provider()
    session = provider.create_checkout(ctx.org_slug, req.plan)
    audit(
        db,
        action="BILLING_CHECKOUT",
        actor=ctx.user_email,
        org_id=ctx.org_id,
        entity_type="subscription",
        meta={"plan": req.plan, "provider": provider.name},
    )
    db.commit()
    return session


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """Provider webhook. Mock provider accepts any event; Stripe verifies signature."""
    provider = get_billing_provider()
    payload = await request.json()
    signature = request.headers.get("stripe-signature")
    result = provider.handle_webhook(payload, signature)
    audit(db, action="BILLING_WEBHOOK", actor=provider.name, meta={"type": result.get("type")})
    db.commit()
    return result
