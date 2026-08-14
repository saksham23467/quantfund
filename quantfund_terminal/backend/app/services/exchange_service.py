"""Research Dataset Exchange — catalog + provenance + certification status.

Certification status is authoritative: for the flagship dataset it mirrors the
REAL core report; the checker itself is never invoked to mutate a verdict here.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.db.models import Certification, Dataset


def _latest_cert(db: Session, dataset_pk: int) -> Certification | None:
    return db.execute(
        select(Certification)
        .where(Certification.dataset_pk == dataset_pk)
        .order_by(Certification.generated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _row(db: Session, d: Dataset) -> dict:
    c = _latest_cert(db, d.id)
    return {
        "dataset_id": d.dataset_id,
        "version": d.dataset_version,
        "title": d.title,
        "asset_class": d.asset_class,
        "source_name": d.source_name,
        "source_type": d.source_type,
        "source_grade": d.source_grade,
        "data_class": d.data_class,
        "coverage": {
            "start": d.coverage_start.isoformat() if d.coverage_start else None,
            "end": d.coverage_end.isoformat() if d.coverage_end else None,
        },
        "content_hash": d.content_hash,
        "immutable": d.immutable,
        "certification": {
            "verdict": c.verdict if c else "DEVELOPMENT_ONLY",
            "research_eligible": bool(c.research_eligible) if c else False,
            "membership_coverage_ratio": c.membership_coverage_ratio if c else None,
            "instrument_identity_coverage": c.instrument_identity_coverage if c else None,
            "delisted_coverage": c.delisted_coverage if c else None,
            "corporate_action_coverage": c.corporate_action_coverage if c else None,
            "calendar_verified": c.calendar_verified if c else None,
            "leakage_safe": c.leakage_safe if c else None,
            "reproducible": c.reproducible if c else None,
            "blockers": c.blockers if c else [],
        },
    }


def list_datasets(db: Session) -> dict:
    datasets = db.execute(select(Dataset).order_by(Dataset.created_at)).scalars().all()
    rows = [_row(db, d) for d in datasets]
    eligible = sum(1 for r in rows if r["certification"]["research_eligible"])
    return {
        "count": len(rows),
        "research_eligible_count": eligible,
        "development_only_count": len(rows) - eligible,
        "datasets": rows,
        "note": (
            "Certification status is authoritative and fail-closed. No dataset is "
            "RESEARCH_ELIGIBLE until an authoritative source is ingested and certified."
        ),
    }


def get_dataset(db: Session, dataset_id: str) -> dict | None:
    d = db.execute(
        select(Dataset).where(Dataset.dataset_id == dataset_id).order_by(Dataset.dataset_version.desc())
    ).scalars().first()
    return _row(db, d) if d else None
