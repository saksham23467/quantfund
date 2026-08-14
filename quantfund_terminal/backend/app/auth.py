"""Multi-tenant context + RBAC.

DEMO auth: the tenant/user/role are read from request headers
(`X-Org-Slug`, `X-User-Email`, `X-Role`) with safe demo defaults. In production
these are derived from a verified OIDC/JWT (Auth0/Cognito) — the dependency
signature stays identical, so routers do not change.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.db import get_db
from quantfund_terminal.backend.app.db.models import Org, User

ROLE_RANK = {"viewer": 0, "analyst": 1, "pm": 2, "admin": 3}


@dataclass
class TenantContext:
    org_id: int | None
    org_slug: str
    user_email: str
    role: str

    def can(self, min_role: str) -> bool:
        return ROLE_RANK.get(self.role, 0) >= ROLE_RANK.get(min_role, 99)


def get_context(
    db: Session = Depends(get_db),
    x_org_slug: str = Header(default="demo-capital"),
    x_user_email: str = Header(default="analyst@demo-capital.in"),
    x_role: str = Header(default="analyst"),
) -> TenantContext:
    role = x_role if x_role in ROLE_RANK else "viewer"
    org = db.execute(select(Org).where(Org.slug == x_org_slug)).scalar_one_or_none()
    return TenantContext(
        org_id=org.id if org else None,
        org_slug=x_org_slug,
        user_email=x_user_email,
        role=role,
    )


def require_role(min_role: str):
    def _dep(ctx: TenantContext = Depends(get_context)) -> TenantContext:
        if not ctx.can(min_role):
            raise HTTPException(
                status_code=403,
                detail=f"role '{ctx.role}' insufficient (requires '{min_role}')",
            )
        return ctx

    return _dep


__all__ = ["TenantContext", "get_context", "require_role", "User", "ROLE_RANK"]
