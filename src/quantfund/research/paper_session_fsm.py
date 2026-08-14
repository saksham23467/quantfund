"""Paper validation session state machine (Phase 10).

CREATED → ELIGIBILITY_CHECKED → READY → RUNNING → RECONCILING
→ COMPLETED → EVALUATED → PASSED | FAILED

No automatic transition to live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PaperValidationState(str, Enum):
    CREATED = "CREATED"
    ELIGIBILITY_CHECKED = "ELIGIBILITY_CHECKED"
    READY = "READY"
    RUNNING = "RUNNING"
    RECONCILING = "RECONCILING"
    COMPLETED = "COMPLETED"
    EVALUATED = "EVALUATED"
    PASSED = "PASSED"
    FAILED = "FAILED"


_ALLOWED: dict[PaperValidationState, set[PaperValidationState]] = {
    PaperValidationState.CREATED: {
        PaperValidationState.ELIGIBILITY_CHECKED,
        PaperValidationState.FAILED,
    },
    PaperValidationState.ELIGIBILITY_CHECKED: {
        PaperValidationState.READY,
        PaperValidationState.FAILED,
    },
    PaperValidationState.READY: {
        PaperValidationState.RUNNING,
        PaperValidationState.FAILED,
    },
    PaperValidationState.RUNNING: {
        PaperValidationState.RECONCILING,
        PaperValidationState.FAILED,
    },
    PaperValidationState.RECONCILING: {
        PaperValidationState.COMPLETED,
        PaperValidationState.FAILED,
    },
    PaperValidationState.COMPLETED: {
        PaperValidationState.EVALUATED,
        PaperValidationState.FAILED,
    },
    PaperValidationState.EVALUATED: {
        PaperValidationState.PASSED,
        PaperValidationState.FAILED,
    },
    PaperValidationState.PASSED: set(),
    PaperValidationState.FAILED: set(),
}


class IllegalPaperSessionTransition(ValueError):
    pass


@dataclass
class PaperSessionFSM:
    session_id: str
    state: PaperValidationState = PaperValidationState.CREATED
    history: list[dict[str, Any]] = field(default_factory=list)
    fail_reason: str | None = None

    def transition(
        self,
        target: PaperValidationState,
        *,
        reason: str | None = None,
    ) -> PaperValidationState:
        if target == PaperValidationState.FAILED:
            # Fail-closed from any non-terminal state
            if self.state in {
                PaperValidationState.PASSED,
                PaperValidationState.FAILED,
            }:
                raise IllegalPaperSessionTransition(
                    f"cannot fail from terminal state {self.state.value}"
                )
            self.history.append(
                {
                    "from": self.state.value,
                    "to": target.value,
                    "reason": reason or "fail_closed",
                }
            )
            self.state = target
            self.fail_reason = reason
            return self.state

        allowed = _ALLOWED.get(self.state, set())
        if target not in allowed:
            raise IllegalPaperSessionTransition(
                f"illegal transition {self.state.value} → {target.value}"
            )
        self.history.append(
            {
                "from": self.state.value,
                "to": target.value,
                "reason": reason,
            }
        )
        self.state = target
        return self.state

    def fail(self, reason: str) -> PaperValidationState:
        return self.transition(PaperValidationState.FAILED, reason=reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "fail_reason": self.fail_reason,
            "history": list(self.history),
            "live_transition": False,
        }
