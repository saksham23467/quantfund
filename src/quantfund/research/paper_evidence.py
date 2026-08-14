"""Immutable paper-performance evidence built from Phase 8 session artifacts.

Does not duplicate the paper ledger/audit — wraps and references them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quantfund.data.ingest.checksums import hash_json
from quantfund.paper.models import state_hash
from quantfund.paper.session import PaperSessionResult


PAPER_EVIDENCE_SCHEMA = "paper_evidence_record_v1"


class PaperEvidenceRecord(BaseModel):
    """Immutable paper evidence artifact for promotion / live-candidate gates."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = PAPER_EVIDENCE_SCHEMA
    paper_evidence_id: str
    session_id: str
    strategy_id: str
    strategy_version: str
    dataset_id: str | None = None
    dataset_version: str | None = None
    data_source: str = "paper_replay"
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: float = 0.0
    initial_capital: float
    order_count: int = 0
    fill_count: int = 0
    trade_count: int = 0
    fees: float = 0.0
    slippage: float = 0.0
    mean_slippage_bps: float | None = None
    equity_curve: list[float] = Field(default_factory=list)
    max_drawdown: float = 0.0
    turnover: float = 0.0
    risk_events: list[dict[str, Any]] = Field(default_factory=list)
    kill_switch_events: list[dict[str, Any]] = Field(default_factory=list)
    reconciliation_ok: bool = False
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    execution_latency_ms_mean: float | None = None
    data_quality_events: list[dict[str, Any]] = Field(default_factory=list)
    risk_limit_violations: int = 0
    reconciliation_failures: int = 0
    data_quality_incidents: int = 0
    execution_failures: int = 0
    kill_switch_incidents: int = 0
    session_count: int = 1
    paper_eligible: bool = False
    acceptance_evidence_id: str | None = None
    state_hash: str | None = None
    audit_event_count: int = 0
    config_refs: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_digest: str
    recorded_at: datetime
    extras: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def evidence_metrics_for_policy(self) -> dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "session_count": self.session_count,
            "n_sessions": self.session_count,
            "trade_count": self.trade_count,
            "n_trades": self.trade_count,
            "max_drawdown": self.max_drawdown,
            "turnover": self.turnover,
            "mean_slippage_bps": self.mean_slippage_bps,
            "risk_limit_violations": self.risk_limit_violations,
            "reconciliation_failures": self.reconciliation_failures,
            "data_quality_incidents": self.data_quality_incidents,
            "execution_failures": self.execution_failures,
            "kill_switch_incidents": self.kill_switch_incidents,
            "reconciliation_ok": self.reconciliation_ok,
            "claims_profitability": False,
        }


def make_paper_evidence_id(
    *,
    session_id: str,
    strategy_id: str,
    strategy_version: str,
    state_hash_value: str | None,
) -> str:
    return hash_json(
        {
            "session_id": session_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "state_hash": state_hash_value,
        }
    )[:32]


def _max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for x in equity:
        peak = max(peak, x)
        if peak > 0:
            max_dd = max(max_dd, (peak - x) / peak)
    return float(max_dd)


def _turnover_from_fills(fills: list[Any], initial_capital: float) -> float:
    if initial_capital <= 0 or not fills:
        return 0.0
    notional = 0.0
    for f in fills:
        px = float(getattr(f, "price", 0.0) or 0.0)
        qty = float(getattr(f, "quantity", 0.0) or 0.0)
        notional += abs(px * qty)
    return float(notional / initial_capital)


def build_paper_evidence_from_session(
    result: PaperSessionResult,
    *,
    strategy_id: str,
    strategy_version: str,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
    data_source: str = "paper_replay",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    acceptance_evidence_id: str | None = None,
    config_refs: dict[str, Any] | None = None,
    equity_curve: list[float] | None = None,
    risk_events: list[dict[str, Any]] | None = None,
    kill_switch_events: list[dict[str, Any]] | None = None,
    data_quality_events: list[dict[str, Any]] | None = None,
    execution_latency_ms_mean: float | None = None,
    mean_slippage_bps: float | None = None,
    extras: dict[str, Any] | None = None,
) -> PaperEvidenceRecord:
    fills = list(result.fills)
    fees = float(
        sum(float(getattr(f, "transaction_cost", 0.0) or 0.0) for f in fills)
    )
    slip_total = float(
        sum(float(getattr(f, "slippage_per_unit", 0.0) or 0.0) for f in fills)
    )
    curve = list(equity_curve or [])
    if not curve and result.snapshot.get("equity") is not None:
        curve = [float(result.snapshot["equity"])]
    initial = float(result.snapshot.get("initial_cash") or 100_000.0)
    if "cash" in result.snapshot and not curve:
        curve = [initial, float(result.snapshot.get("equity", initial))]

    start = start_time
    end = end_time
    duration = 0.0
    if start and end:
        duration = max(0.0, (end - start).total_seconds())

    recon = result.reconciliation.to_dict()
    recon_ok = bool(result.reconciliation.ok)
    risk_ev = list(risk_events or [])
    kill_ev = list(kill_switch_events or [])
    dq_ev = list(data_quality_events or [])
    exec_fail = 1 if result.halted and result.halt_reason else 0

    evidence_id = make_paper_evidence_id(
        session_id=result.session_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        state_hash_value=result.state_hash,
    )
    provisional = {
        "schema_version": PAPER_EVIDENCE_SCHEMA,
        "paper_evidence_id": evidence_id,
        "session_id": result.session_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "data_source": data_source,
        "duration_seconds": duration,
        "initial_capital": initial,
        "order_count": len(result.orders),
        "fill_count": len(fills),
        "trade_count": len(fills),
        "fees": fees,
        "slippage": slip_total,
        "mean_slippage_bps": mean_slippage_bps,
        "equity_curve": curve,
        "max_drawdown": _max_drawdown(curve),
        "turnover": _turnover_from_fills(fills, initial),
        "risk_events": risk_ev,
        "kill_switch_events": kill_ev,
        "reconciliation_ok": recon_ok,
        "reconciliation": recon,
        "execution_latency_ms_mean": execution_latency_ms_mean,
        "data_quality_events": dq_ev,
        "risk_limit_violations": len(risk_ev),
        "reconciliation_failures": 0 if recon_ok else 1,
        "data_quality_incidents": len(dq_ev),
        "execution_failures": exec_fail,
        "kill_switch_incidents": len(kill_ev),
        "session_count": 1,
        "paper_eligible": result.paper_eligible,
        "acceptance_evidence_id": acceptance_evidence_id,
        "state_hash": result.state_hash,
        "audit_event_count": result.audit_event_count,
        "config_refs": dict(config_refs or {}),
        "metrics": {
            "halted": result.halted,
            "halt_reason": result.halt_reason,
            "mode": result.mode.value,
        },
    }
    digest = state_hash(
        {k: v for k, v in provisional.items() if k not in {"extras"}}
    )
    return PaperEvidenceRecord(
        **provisional,
        start_time=start,
        end_time=end,
        artifact_digest=digest,
        recorded_at=datetime.now(timezone.utc),
        extras=dict(extras or {}),
    )


def verify_paper_evidence(record: PaperEvidenceRecord) -> list[str]:
    blockers: list[str] = []
    expected = make_paper_evidence_id(
        session_id=record.session_id,
        strategy_id=record.strategy_id,
        strategy_version=record.strategy_version,
        state_hash_value=record.state_hash,
    )
    if record.paper_evidence_id != expected:
        blockers.append("paper_evidence_id_mismatch")
    if not record.reconciliation_ok:
        blockers.append("reconciliation_failed")
    if record.reconciliation_failures > 0:
        blockers.append("unresolved_reconciliation")
    return blockers


def write_paper_evidence(path: Path, record: PaperEvidenceRecord) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record.to_dict(), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def load_paper_evidence(path: Path) -> PaperEvidenceRecord:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return PaperEvidenceRecord.model_validate(raw)


def aggregate_paper_evidence(
    records: list[PaperEvidenceRecord],
) -> dict[str, Any]:
    """Aggregate multi-session evidence for paper_policy evaluation."""
    if not records:
        return {}
    return {
        "duration_seconds": sum(r.duration_seconds for r in records),
        "session_count": len(records),
        "n_sessions": len(records),
        "trade_count": sum(r.trade_count for r in records),
        "n_trades": sum(r.trade_count for r in records),
        "max_drawdown": max((r.max_drawdown for r in records), default=0.0),
        "turnover": sum(r.turnover for r in records) / len(records),
        "mean_slippage_bps": (
            sum(r.mean_slippage_bps or 0.0 for r in records) / len(records)
        ),
        "risk_limit_violations": sum(r.risk_limit_violations for r in records),
        "reconciliation_failures": sum(r.reconciliation_failures for r in records),
        "data_quality_incidents": sum(r.data_quality_incidents for r in records),
        "execution_failures": sum(r.execution_failures for r in records),
        "kill_switch_incidents": sum(r.kill_switch_incidents for r in records),
        "reconciliation_ok": all(r.reconciliation_ok for r in records),
        "claims_profitability": False,
    }
