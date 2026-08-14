"""LIVE_TRADING feature flag — default false; env alone never enables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LiveTradingFlag:
    enabled: bool = False
    source: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return {"LIVE_TRADING": self.enabled, "source": self.source}


def resolve_live_trading_flag(
    *,
    explicit: bool | None = None,
    env: dict[str, str] | None = None,
) -> LiveTradingFlag:
    """Explicit argument wins. Env LIVE_TRADING=true alone is NOT sufficient
    to authorize orders — activation gates still required — but we record it.
    Default is always False when unset.
    """
    if explicit is True:
        return LiveTradingFlag(enabled=True, source="explicit")
    if explicit is False:
        return LiveTradingFlag(enabled=False, source="explicit")
    e = env if env is not None else dict(os.environ)
    raw = (e.get("LIVE_TRADING") or e.get("QUANTFUND_LIVE_TRADING") or "").strip().lower()
    if raw in {"1", "true", "yes"}:
        # Recorded but must still pass activation — never implicit authorization
        return LiveTradingFlag(enabled=True, source="environment_untrusted")
    return LiveTradingFlag(enabled=False, source="default")


def env_alone_cannot_authorize(env: dict[str, str] | None = None) -> bool:
    """Invariant: presence of LIVE_TRADING in env is never enough by itself."""
    flag = resolve_live_trading_flag(env=env)
    if flag.source == "environment_untrusted" and flag.enabled:
        return True  # needs activation
    return True
