"""Research Copilot v2 — same deterministic planner, now tenant-aware and
audit-logged with an immutable research record."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.auth import TenantContext, get_context
from quantfund_terminal.backend.app.db import get_db
from quantfund_terminal.backend.app.schemas import CopilotRequest
from quantfund_terminal.backend.app.services.records_service import append_record, audit
from quantfund_terminal.copilot import plan

router = APIRouter(prefix="/api/v2", tags=["copilot_v2"])


@router.post("/copilot")
def copilot(
    req: CopilotRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_context),
) -> dict:
    result = plan(req.prompt).as_dict()
    rec = append_record(
        db,
        kind="copilot_query",
        ref_id=ctx.user_email,
        org_id=ctx.org_id,
        payload={"prompt": req.prompt, "intent": result["intent"]},
    )
    audit(
        db,
        action="COPILOT_QUERY",
        actor=ctx.user_email,
        org_id=ctx.org_id,
        entity_type="copilot",
        entity_id=str(rec.id),
        meta={"intent": result["intent"]},
    )
    db.commit()
    result["record_hash"] = rec.content_hash
    result["org"] = ctx.org_slug
    return result
