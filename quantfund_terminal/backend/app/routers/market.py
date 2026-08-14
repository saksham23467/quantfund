"""Market Dashboard endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from quantfund_terminal.backend.app.services import market_service

router = APIRouter(tags=["market"])


@router.get("/api/market")
def market() -> dict:
    return market_service.get_market_snapshot()
