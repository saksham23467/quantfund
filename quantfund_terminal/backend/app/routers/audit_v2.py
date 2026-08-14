"""Immutable research records + audit log + chain verification."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.auth import TenantContext, get_context
from quantfund_terminal.backend.app.db import get_db
from quantfund_terminal.backend.app.db.models import AuditLog, ResearchRecord
from quantfund_terminal.backend.app.services.records_service import verify_chain

router = APIRouter(prefix="/api/v2/audit", tags=["audit_v2"])


@router.get("/records")
def records(
    limit: int = 50, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_context)
) -> dict:
    rows = (
        db.execute(select(ResearchRecord).order_by(ResearchRecord.id.desc()).limit(limit))
        .scalars()
        .all()
    )
    return {
        "records": [
            {
                "id": r.id,
                "kind": r.kind,
                "ref_id": r.ref_id,
                "content_hash": r.content_hash,
                "prev_hash": r.prev_hash,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/verify")
def verify(db: Session = Depends(get_db)) -> dict:
    return verify_chain(db)


@router.get("/log")
def log(
    limit: int = 100, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_context)
) -> dict:
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    rows = db.execute(q).scalars().all()
    return {
        "entries": [
            {
                "id": e.id,
                "actor": e.actor,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "org_id": e.org_id,
                "created_at": e.created_at.isoformat(),
            }
            for e in rows
        ]
    }
