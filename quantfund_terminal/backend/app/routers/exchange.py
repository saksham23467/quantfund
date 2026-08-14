"""Research Dataset Exchange endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.db import get_db
from quantfund_terminal.backend.app.services import exchange_service

router = APIRouter(prefix="/api/v2", tags=["dataset_exchange"])


@router.get("/datasets")
def datasets(db: Session = Depends(get_db)) -> dict:
    return exchange_service.list_datasets(db)


@router.get("/datasets/{dataset_id}")
def dataset(dataset_id: str, db: Session = Depends(get_db)) -> dict:
    row = exchange_service.get_dataset(db, dataset_id)
    if not row:
        raise HTTPException(status_code=404, detail="dataset not found")
    return row
