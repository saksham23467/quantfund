"""Investor Dashboard endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from quantfund_terminal.backend.app.db import get_db
from quantfund_terminal.backend.app.services import investor_service

router = APIRouter(prefix="/api/v2", tags=["investor"])


@router.get("/investor")
def investor(db: Session = Depends(get_db)) -> dict:
    return investor_service.investor_dashboard(db)
