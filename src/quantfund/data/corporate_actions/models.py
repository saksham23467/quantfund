"""Corporate action schema.

Phase 1 supports modeling splits, bonus issues, and dividends.
Mergers/demergers are stored and flagged — no automatic price reconstruction.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CorporateActionType(str, Enum):
    SPLIT = "split"
    BONUS = "bonus"
    DIVIDEND = "dividend"
    MERGER = "merger"
    DEMERGER = "demerger"
    SYMBOL_CHANGE = "symbol_change"
    RIGHTS = "rights"
    FACE_VALUE_CHANGE = "face_value_change"
    BUYBACK = "buyback"
    OTHER = "other"


class CorporateAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    instrument_id: str
    symbol: str
    action_type: CorporateActionType
    ex_date: date
    record_date: date | None = None
    announcement_date: date | None = None
    # Split/bonus: new/old share ratio. Example 2-for-1 → ratio_num=2, ratio_den=1.
    ratio_num: float | None = None
    ratio_den: float | None = None
    cash_amount: float | None = None  # dividend per share
    currency: str = "INR"
    successor_instrument_id: str | None = None
    source: str = "unknown"
    source_ref: str | None = None
    verified: bool = False
    requires_manual_treatment: bool = False
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""

    @model_validator(mode="after")
    def flag_complex_actions(self) -> CorporateAction:
        if self.action_type in {
            CorporateActionType.MERGER,
            CorporateActionType.DEMERGER,
            CorporateActionType.FACE_VALUE_CHANGE,
            CorporateActionType.BUYBACK,
            CorporateActionType.RIGHTS,
        }:
            object.__setattr__(self, "requires_manual_treatment", True)
        parse_unknown = self.raw_payload.get("parse_status") == "UNKNOWN"
        if self.action_type in {CorporateActionType.SPLIT, CorporateActionType.BONUS}:
            if self.ratio_num is None or self.ratio_den is None or self.ratio_den == 0:
                if parse_unknown:
                    object.__setattr__(self, "requires_manual_treatment", True)
                else:
                    raise ValueError("split/bonus requires ratio_num and non-zero ratio_den")
        if self.action_type == CorporateActionType.DIVIDEND and self.cash_amount is None:
            if parse_unknown:
                object.__setattr__(self, "requires_manual_treatment", True)
            else:
                raise ValueError("dividend requires cash_amount")
        return self

    @property
    def split_factor(self) -> float | None:
        """Shares multiplier on ex-date (2-for-1 → 2.0)."""
        if self.ratio_num is None or self.ratio_den is None or self.ratio_den == 0:
            return None
        return float(self.ratio_num) / float(self.ratio_den)
