"""Explicit adjustment policies — never silent."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AdjustmentPolicy(BaseModel):
    """Declared corporate-action adjustment policy for a research dataset.

    Default QuantFund Phase 1 policy:
    - split adjusted
    - bonus adjusted
    - dividends tracked separately (NOT applied to adjusted OHLC)
    - RAW OHLC never modified
    """

    model_config = ConfigDict(frozen=True)

    policy_id: str = "split_bonus_v1"
    policy_version: str = "1.0.0"
    adjust_splits: bool = True
    adjust_bonus: bool = True
    adjust_dividends_in_ohlc: bool = False
    track_dividends_separately: bool = True
    # Backward adjustment: historical prices divided by cumulative future factors.
    method: str = "backward_cumulative_split_bonus"
    description: str = (
        "Backward-adjust OHLC for splits and bonus issues only. "
        "Dividends are stored separately and excluded from adjusted OHLC. "
        "RAW open/high/low/close are never overwritten."
    )

    def to_manifest_dict(self) -> dict:
        return self.model_dump()


def default_split_bonus_policy() -> AdjustmentPolicy:
    return AdjustmentPolicy()
