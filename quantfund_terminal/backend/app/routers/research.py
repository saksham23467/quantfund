"""Research Lab: create no-code strategy drafts."""

from __future__ import annotations

from fastapi import APIRouter

from quantfund_terminal.backend.app.schemas import StrategyCreateRequest
from quantfund_terminal.backend.app.services import strategy_store

router = APIRouter(tags=["research"])


@router.get("/api/strategies")
def list_strategies() -> dict:
    return {
        "families": sorted(strategy_store.VALID_FAMILIES),
        "strategies": strategy_store.list_strategies(),
    }


@router.post("/api/strategies")
def create_strategy(req: StrategyCreateRequest) -> dict:
    return strategy_store.create_strategy(req.name, req.family, req.params)
