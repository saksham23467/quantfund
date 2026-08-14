"""Explicit operator approval — never automatic, never AI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quantfund.paper.models import deterministic_id


@dataclass
class OperatorApprovalRecord:
    approved: bool
    operator_id: str
    reason: str
    approval_id: str
    at: str
    session_id: str
    strategy_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "operator_id": self.operator_id,
            "reason": self.reason,
            "approval_id": self.approval_id,
            "at": self.at,
            "session_id": self.session_id,
            "strategy_id": self.strategy_id,
        }


@dataclass
class OperatorApprovalGate:
    """Human approval artifact required before execution rung."""

    records: list[OperatorApprovalRecord] = field(default_factory=list)

    def approve(
        self,
        *,
        session_id: str,
        operator_id: str,
        reason: str,
        strategy_id: str | None = None,
    ) -> OperatorApprovalRecord:
        if not operator_id or not str(operator_id).strip():
            raise ValueError("operator_id_required")
        if not reason or not str(reason).strip():
            raise ValueError("approval_reason_required")
        if operator_id.lower() in {"ai", "llm", "generator", "system_auto"}:
            raise ValueError("ai_operator_forbidden")
        at = datetime.now(timezone.utc).isoformat()
        approval_id = deterministic_id(
            "op_approval", session_id, operator_id, reason, at[:19]
        )
        # Use stable id without wall-clock for determinism in tests when reason fixed
        approval_id = deterministic_id("op_approval", session_id, operator_id, reason)
        rec = OperatorApprovalRecord(
            approved=True,
            operator_id=operator_id,
            reason=reason,
            approval_id=approval_id,
            at=at,
            session_id=session_id,
            strategy_id=strategy_id,
        )
        self.records.append(rec)
        return rec

    def is_approved(self, session_id: str) -> bool:
        return any(r.approved and r.session_id == session_id for r in self.records)

    def require_approved(self, session_id: str) -> None:
        if not self.is_approved(session_id):
            raise PermissionError("operator_approval_required")
