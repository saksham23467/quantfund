"""Per-type corporate-action coverage derivation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.policy import CorporateActionCoverage


class ActionTypeCoverage(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    FULL_VERIFIED = "full_verified"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class CorporateActionCoverageReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    splits: ActionTypeCoverage = ActionTypeCoverage.NONE
    bonuses: ActionTypeCoverage = ActionTypeCoverage.NONE
    dividends: ActionTypeCoverage = ActionTypeCoverage.NONE
    symbol_changes: ActionTypeCoverage = ActionTypeCoverage.NONE
    mergers: ActionTypeCoverage = ActionTypeCoverage.NONE
    demergers: ActionTypeCoverage = ActionTypeCoverage.NONE
    overall: str = CorporateActionCoverage.NONE.value
    action_count: int = 0
    unverified_count: int = 0
    notes: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        # Phase 7 explicit per-type aliases for certification reports
        data["split_coverage"] = data["splits"]
        data["bonus_coverage"] = data["bonuses"]
        data["dividend_coverage"] = data["dividends"]
        data["identity_event_coverage"] = data["symbol_changes"]
        data["merger_coverage"] = data["mergers"]
        data["demerger_coverage"] = data["demergers"]
        return data


def _coverage_for(
    actions: list[CorporateAction],
    action_type: CorporateActionType,
    *,
    complex_manual: bool = False,
) -> ActionTypeCoverage:
    subset = [a for a in actions if a.action_type == action_type]
    if not subset:
        return ActionTypeCoverage.NONE
    if complex_manual:
        if any(a.requires_manual_treatment for a in subset):
            if all(a.verified for a in subset) and all(
                a.raw_payload.get("treatment") == "verified_mapping" for a in subset
            ):
                return ActionTypeCoverage.FULL_VERIFIED
            return ActionTypeCoverage.MANUAL_REVIEW_REQUIRED
        return ActionTypeCoverage.UNSUPPORTED
    if all(a.verified for a in subset):
        return ActionTypeCoverage.FULL_VERIFIED
    return ActionTypeCoverage.PARTIAL


def derive_ca_coverage_report(
    actions: list[CorporateAction] | None,
    *,
    source_grade: str | None = None,
) -> CorporateActionCoverageReport:
    actions = list(actions or [])
    notes: list[str] = []
    if source_grade in {"synthetic", "non_exchange"}:
        notes.append(
            "synthetic/non_exchange sources cannot claim overall full_verified"
        )

    splits = _coverage_for(actions, CorporateActionType.SPLIT)
    bonuses = _coverage_for(actions, CorporateActionType.BONUS)
    dividends = _coverage_for(actions, CorporateActionType.DIVIDEND)
    symbol_changes = _coverage_for(actions, CorporateActionType.SYMBOL_CHANGE)
    mergers = _coverage_for(actions, CorporateActionType.MERGER, complex_manual=True)
    demergers = _coverage_for(actions, CorporateActionType.DEMERGER, complex_manual=True)

    unverified = sum(1 for a in actions if not a.verified)

    # Overall mapping for ResearchEligibilityChecker (existing vocabulary)
    type_vals = {a.action_type for a in actions}
    needed = {
        CorporateActionType.SPLIT,
        CorporateActionType.BONUS,
        CorporateActionType.DIVIDEND,
    }
    if not actions:
        overall = CorporateActionCoverage.NONE.value
    elif source_grade in {"synthetic", "non_exchange", None}:
        if needed.issubset(type_vals):
            overall = CorporateActionCoverage.SPLITS_BONUS_DIVIDENDS.value
        elif type_vals & needed:
            overall = CorporateActionCoverage.PARTIAL.value
        else:
            overall = CorporateActionCoverage.PARTIAL.value
    elif (
        needed.issubset(type_vals)
        and splits == ActionTypeCoverage.FULL_VERIFIED
        and bonuses == ActionTypeCoverage.FULL_VERIFIED
        and dividends == ActionTypeCoverage.FULL_VERIFIED
        and unverified == 0
    ):
        overall = CorporateActionCoverage.FULL_VERIFIED.value
    elif type_vals & needed:
        overall = CorporateActionCoverage.SPLITS_BONUS_DIVIDENDS.value
    else:
        overall = CorporateActionCoverage.PARTIAL.value

    if mergers in {
        ActionTypeCoverage.MANUAL_REVIEW_REQUIRED,
        ActionTypeCoverage.UNSUPPORTED,
    }:
        notes.append("mergers require manual treatment — no automatic OHLC reconstruction")
    if demergers in {
        ActionTypeCoverage.MANUAL_REVIEW_REQUIRED,
        ActionTypeCoverage.UNSUPPORTED,
    }:
        notes.append("demergers require manual treatment — no automatic OHLC reconstruction")

    return CorporateActionCoverageReport(
        splits=splits,
        bonuses=bonuses,
        dividends=dividends,
        symbol_changes=symbol_changes,
        mergers=mergers,
        demergers=demergers,
        overall=overall,
        action_count=len(actions),
        unverified_count=unverified,
        notes=notes,
    )
