"""Immutable, hash-linked research records (reproducibility proofs)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.db.models import AuditLog, ResearchRecord
from quantfund_terminal.backend.app.util.hashing import content_hash


def append_record(
    db: Session, *, kind: str, ref_id: str, payload: dict, org_id: int | None = None
) -> ResearchRecord:
    """Append a record whose hash chains onto the previous record's hash."""
    prev = db.execute(
        select(ResearchRecord).order_by(ResearchRecord.id.desc()).limit(1)
    ).scalar_one_or_none()
    prev_hash = prev.content_hash if prev else None
    chained = {"kind": kind, "ref_id": ref_id, "payload": payload, "prev_hash": prev_hash}
    rec = ResearchRecord(
        org_id=org_id,
        kind=kind,
        ref_id=ref_id,
        content_hash=content_hash(chained),
        prev_hash=prev_hash,
        payload=payload,
    )
    db.add(rec)
    db.flush()
    return rec


def verify_chain(db: Session) -> dict:
    """Recompute the chain and report the first break (if any)."""
    records = db.execute(select(ResearchRecord).order_by(ResearchRecord.id)).scalars().all()
    prev_hash = None
    broken_at = None
    for rec in records:
        expected = content_hash(
            {
                "kind": rec.kind,
                "ref_id": rec.ref_id,
                "payload": rec.payload,
                "prev_hash": prev_hash,
            }
        )
        if expected != rec.content_hash or rec.prev_hash != prev_hash:
            broken_at = rec.id
            break
        prev_hash = rec.content_hash
    return {
        "total_records": len(records),
        "intact": broken_at is None,
        "broken_at_id": broken_at,
        "head_hash": records[-1].content_hash if records else None,
    }


def audit(
    db: Session,
    *,
    action: str,
    actor: str = "system",
    org_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    meta: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            org_id=org_id,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            meta=meta or {},
        )
    )
    db.flush()
