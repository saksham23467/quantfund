"""Phase 15 session state machine — no path to live trading."""

from __future__ import annotations

from quantfund.phase15.models import SessionState

_ALLOWED: dict[SessionState, frozenset[SessionState]] = {
    SessionState.CREATED: frozenset(
        {SessionState.PREFLIGHT, SessionState.FAILED_SAFE}
    ),
    SessionState.PREFLIGHT: frozenset(
        {SessionState.CONNECTED, SessionState.FAILED_SAFE}
    ),
    SessionState.CONNECTED: frozenset(
        {SessionState.WARMING_UP, SessionState.FAILED_SAFE}
    ),
    SessionState.WARMING_UP: frozenset(
        {
            SessionState.RUNNING_SHADOW,
            SessionState.PAUSED,
            SessionState.FAILED_SAFE,
            SessionState.SESSION_INVALIDATED,
        }
    ),
    SessionState.RUNNING_SHADOW: frozenset(
        {
            SessionState.PAUSED,
            SessionState.STOPPING,
            SessionState.FAILED_SAFE,
            SessionState.SESSION_INVALIDATED,
        }
    ),
    SessionState.PAUSED: frozenset(
        {
            SessionState.RUNNING_SHADOW,
            SessionState.STOPPING,
            SessionState.FAILED_SAFE,
            SessionState.SESSION_INVALIDATED,
        }
    ),
    SessionState.STOPPING: frozenset(
        {SessionState.COMPLETED, SessionState.FAILED_SAFE}
    ),
    SessionState.COMPLETED: frozenset(),
    SessionState.FAILED_SAFE: frozenset(),
    SessionState.SESSION_INVALIDATED: frozenset(
        {SessionState.STOPPING, SessionState.FAILED_SAFE}
    ),
}


class SessionStateMachine:
    def __init__(self, initial: SessionState = SessionState.CREATED) -> None:
        self.state = initial
        self.history: list[str] = [initial.value]

    def transition(self, target: SessionState) -> None:
        if target is SessionState.FAILED_SAFE:
            self.state = target
            self.history.append(target.value)
            return
        allowed = _ALLOWED.get(self.state, frozenset())
        if target not in allowed:
            raise ValueError(
                f"illegal_transition:{self.state.value}->{target.value}"
            )
        self.state = target
        self.history.append(target.value)

    @property
    def allows_shadow_decisions(self) -> bool:
        return self.state is SessionState.RUNNING_SHADOW

    @property
    def is_terminal(self) -> bool:
        return self.state in {
            SessionState.COMPLETED,
            SessionState.FAILED_SAFE,
        }
