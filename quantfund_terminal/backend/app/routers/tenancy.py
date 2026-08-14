"""Multi-tenant identity + admin (orgs/users)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.auth import (
    TenantContext,
    get_context,
    require_role,
)
from quantfund_terminal.backend.app.db import get_db
from quantfund_terminal.backend.app.db.models import Org, Subscription, User
from quantfund_terminal.backend.app.schemas import OrgCreateRequest

router = APIRouter(prefix="/api/v2", tags=["tenancy"])


@router.get("/me")
def me(ctx: TenantContext = Depends(get_context)) -> dict:
    return {
        "org_slug": ctx.org_slug,
        "org_id": ctx.org_id,
        "user_email": ctx.user_email,
        "role": ctx.role,
        "permissions": {
            "view": ctx.can("viewer"),
            "create_strategy": ctx.can("analyst"),
            "publish_marketplace": ctx.can("pm"),
            "admin": ctx.can("admin"),
        },
    }


@router.get("/orgs")
def orgs(db: Session = Depends(get_db), ctx: TenantContext = Depends(require_role("admin"))) -> dict:
    rows = db.execute(select(Org)).scalars().all()
    subs = {s.org_id: s for s in db.execute(select(Subscription)).scalars().all()}
    return {
        "orgs": [
            {
                "id": o.id,
                "name": o.name,
                "slug": o.slug,
                "plan": o.plan,
                "subscription": (
                    {"plan": subs[o.id].plan, "status": subs[o.id].status, "seats": subs[o.id].seats}
                    if o.id in subs
                    else None
                ),
            }
            for o in rows
        ]
    }


@router.post("/orgs")
def create_org(
    req: OrgCreateRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("admin")),
) -> dict:
    org = Org(name=req.name, slug=req.slug, plan=req.plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return {"id": org.id, "slug": org.slug, "name": org.name, "plan": org.plan}


@router.get("/users")
def users(db: Session = Depends(get_db), ctx: TenantContext = Depends(require_role("pm"))) -> dict:
    q = select(User)
    if ctx.org_id:
        q = q.where(User.org_id == ctx.org_id)
    rows = db.execute(q).scalars().all()
    return {"users": [{"email": u.email, "role": u.role, "org_id": u.org_id} for u in rows]}
