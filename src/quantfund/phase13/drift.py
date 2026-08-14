"""Backtest ↔ paper semantic drift for Phase 13 historical replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from quantfund.backtest.engine import BacktestEngine, BacktestConfig, BacktestResult
from quantfund.backtest.broker_sim import SlippageModel
from quantfund.data.models import MarketBar
from quantfund.paper.session import PaperSessionResult
from quantfund.phase11.drift_cert import PaperDriftClass
from quantfund.research.execution_models import resolve_execution_models
from quantfund.strategies.base import Strategy


class Phase13DriftClass(str, Enum):
    NONE = "NONE"
    EXPECTED = "EXPECTED"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class Phase13DriftReport:
    classification: Phase13DriftClass
    findings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    blocks_further_paper: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "findings": list(self.findings),
            "details": dict(self.details),
            "blocks_further_paper": self.blocks_further_paper,
            "claims": "NONE",
        }


def run_backtest_for_drift(
    strategy: Strategy,
    bars: list[MarketBar],
    *,
    initial_capital: float,
    cost_model_id: str = "equity_delivery_v1",
    slippage_model_id: str = "fixed_bps_5",
) -> BacktestResult:
    cost, slip = resolve_execution_models(
        cost_model=cost_model_id, slippage_model=slippage_model_id
    )
    engine = BacktestEngine(
        strategy,
        config=BacktestConfig(
            initial_capital=initial_capital,
            data_source="yfinance",
            data_version="phase13_validation",
            research_eligibility="development_only",
            source_grade="non_exchange",
        ),
        cost_model=cost,
        slippage_model=slip,
    )
    return engine.run(bars)


def compare_backtest_paper_semantics(
    bt: BacktestResult,
    paper: PaperSessionResult,
    *,
    qty_tol: float = 1e-6,
    price_tol: float = 1e-4,
    cash_tol: float = 0.05,
) -> Phase13DriftReport:
    findings: list[str] = []
    details: dict[str, Any] = {}

    bt_fills = [e for e in bt.events if e.get("type") == "fill"]
    paper_fills = paper.fills

    details["bt_signal_count"] = len(bt.signals)
    details["paper_order_count"] = len(paper.orders)
    details["bt_fill_count"] = len(bt_fills)
    details["paper_fill_count"] = len(paper_fills)
    details["bt_final_equity"] = bt.final_equity
    details["paper_equity"] = paper.snapshot.get("equity")
    details["bt_rejected"] = len(bt.rejected_orders)

    if len(bt_fills) != len(paper_fills):
        findings.append(
            f"fill_count_bt={len(bt_fills)} paper={len(paper_fills)}"
        )

    for i, (be, pf) in enumerate(zip(bt_fills, paper_fills)):
        if abs(float(be["qty"]) - float(pf.quantity)) > qty_tol:
            findings.append(f"qty_mismatch_fill_{i}")
        if abs(float(be["price"]) - float(pf.price)) > price_tol:
            findings.append(f"price_mismatch_fill_{i}")
        # execution timestamp: both next-bar open
        if be.get("timestamp") and pf.timestamp.isoformat() != be["timestamp"]:
            # allow timezone normalization differences only if same instant
            try:
                from datetime import datetime

                bt_ts = datetime.fromisoformat(be["timestamp"])
                if bt_ts != pf.timestamp and bt_ts.replace(tzinfo=pf.timestamp.tzinfo) != pf.timestamp:
                    findings.append(f"exec_ts_mismatch_fill_{i}")
            except Exception:
                findings.append(f"exec_ts_mismatch_fill_{i}")

    pe = paper.snapshot.get("equity")
    if pe is not None and abs(float(pe) - float(bt.final_equity)) > cash_tol:
        findings.append(
            f"equity_mismatch bt={bt.final_equity} paper={pe}"
        )

    pc = paper.snapshot.get("cash")
    if pc is not None and abs(float(pc) - float(bt.portfolio.cash)) > cash_tol:
        findings.append(f"cash_mismatch bt={bt.portfolio.cash} paper={pc}")

    if findings:
        # Semantic mismatches are CRITICAL for historical replay certification
        return Phase13DriftReport(
            classification=Phase13DriftClass.CRITICAL,
            findings=findings,
            details=details,
            blocks_further_paper=True,
        )

    return Phase13DriftReport(
        classification=Phase13DriftClass.NONE,
        findings=[],
        details=details,
        blocks_further_paper=False,
    )


def drift_class_to_phase11(c: Phase13DriftClass) -> PaperDriftClass:
    return PaperDriftClass(c.value)
