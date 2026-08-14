"""Moat endpoints backed by REAL reports: certification, leaderboard, audit."""

from __future__ import annotations

from fastapi import APIRouter

from quantfund_terminal.backend.app.services import (
    audit_service,
    certification_service,
    leaderboard_service,
)

router = APIRouter(tags=["moat"])


@router.get("/api/certification")
def certification() -> dict:
    return certification_service.get_certification()


@router.get("/api/leaderboard")
def leaderboard() -> dict:
    return leaderboard_service.get_leaderboard()


@router.get("/api/audit")
def audit() -> dict:
    return audit_service.get_audit()
