"""Backtest vs paper drift classification for Phase 11."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PaperDriftClass(str, Enum):
    NONE = "NONE"
    EXPECTED = "EXPECTED"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class BacktestPaperDriftReport:
    classification: PaperDriftClass
    findings: list[str] = field(default_factory=list)
    blocks_further_paper: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "findings": list(self.findings),
            "blocks_further_paper": self.blocks_further_paper,
            "details": dict(self.details),
        }


def classify_backtest_paper_drift(
    *,
    signal_count_bt: int,
    signal_count_paper: int,
    order_count_bt: int,
    order_count_paper: int,
    avg_price_delta_bps: float = 0.0,
    cost_delta_ratio: float = 0.0,
    unknown_membership_traded: bool = False,
    future_ca_visible: bool = False,
    calendar_mismatch: bool = False,
) -> BacktestPaperDriftReport:
    findings: list[str] = []
    if unknown_membership_traded:
        findings.append("unknown_membership_traded")
    if future_ca_visible:
        findings.append("future_ca_visibility")
    if calendar_mismatch:
        findings.append("calendar_session_mismatch")

    if findings:
        return BacktestPaperDriftReport(
            classification=PaperDriftClass.CRITICAL,
            findings=findings,
            blocks_further_paper=True,
        )

    if signal_count_bt != signal_count_paper:
        findings.append(
            f"signal_count_bt={signal_count_bt} paper={signal_count_paper}"
        )
    if order_count_bt != order_count_paper:
        findings.append(f"order_count_bt={order_count_bt} paper={order_count_paper}")

    if abs(avg_price_delta_bps) > 50 or abs(cost_delta_ratio) > 0.25:
        findings.append("execution_price_or_cost_divergence")
        return BacktestPaperDriftReport(
            classification=PaperDriftClass.WARNING,
            findings=findings,
            blocks_further_paper=False,
            details={
                "avg_price_delta_bps": avg_price_delta_bps,
                "cost_delta_ratio": cost_delta_ratio,
            },
        )

    if findings:
        # count mismatches without critical flags → expected microstructure diffs
        return BacktestPaperDriftReport(
            classification=PaperDriftClass.EXPECTED,
            findings=findings,
            blocks_further_paper=False,
        )

    return BacktestPaperDriftReport(
        classification=PaperDriftClass.NONE,
        findings=[],
        blocks_further_paper=False,
    )
