"""AI Research Copilot endpoint (deterministic plan generation)."""

from __future__ import annotations

from fastapi import APIRouter

from quantfund_terminal.backend.app.schemas import CopilotRequest
from quantfund_terminal.copilot import plan

router = APIRouter(tags=["copilot"])


@router.post("/api/copilot")
def copilot(req: CopilotRequest) -> dict:
    return plan(req.prompt).as_dict()
