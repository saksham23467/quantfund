"""Versioned paper_policy_v1 — paper evidence → LIVE_ELIGIBILITY_CANDIDATE.

Passing paper policy does NOT authorize live trading or guarantee profitability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


PAPER_POLICY_VERSION = "paper_policy_v1"


class PaperPolicyVerdict(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PaperPolicyV1(BaseModel):
    """Configurable, versioned thresholds for paper → live-candidate."""

    model_config = ConfigDict(frozen=True)

    policy_id: str = PAPER_POLICY_VERSION
    min_session_duration_seconds: float = 60.0
    min_sessions: int = 1
    min_trades: int = 3
    max_drawdown: float = 0.25
    max_risk_limit_violations: int = 0
    max_reconciliation_failures: int = 0
    max_data_quality_incidents: int = 0
    max_execution_failures: int = 0
    max_kill_switch_incidents: int = 0
    max_turnover: float | None = None
    max_slippage_bps_mean: float | None = 50.0
    max_abs_return_divergence: float | None = 0.5
    max_sharpe_divergence: float | None = 2.0
    require_reconciliation_ok: bool = True
    require_no_material_divergence: bool = True
    claim_profitability: bool = False  # always false; policy forbids profit claims


@dataclass
class PaperPolicyDecision:
    verdict: PaperPolicyVerdict
    live_eligibility_candidate: bool
    policy_id: str
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "live_eligibility_candidate": self.live_eligibility_candidate,
            "policy_id": self.policy_id,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "metrics_snapshot": dict(self.metrics_snapshot),
            "claims": "NONE",
            "live_trading": "DISABLED",
            "note": (
                "Paper pass ≠ live authorization; "
                "research acceptance ≠ profitability guarantee"
            ),
        }


def evaluate_paper_policy(
    evidence: dict[str, Any],
    *,
    policy: PaperPolicyV1 | None = None,
    comparison: dict[str, Any] | None = None,
) -> PaperPolicyDecision:
    """Evaluate paper evidence against paper_policy_v1. Fail closed."""
    pol = policy or PaperPolicyV1()
    blockers: list[str] = []
    reasons: list[str] = []

    if not evidence:
        return PaperPolicyDecision(
            verdict=PaperPolicyVerdict.INSUFFICIENT_EVIDENCE,
            live_eligibility_candidate=False,
            policy_id=pol.policy_id,
            blockers=["missing_paper_evidence"],
            reasons=["insufficient_evidence"],
        )

    duration = float(evidence.get("duration_seconds") or 0.0)
    sessions = int(evidence.get("session_count") or evidence.get("n_sessions") or 1)
    trades = int(evidence.get("trade_count") or evidence.get("n_trades") or 0)
    max_dd = float(evidence.get("max_drawdown") or 0.0)
    risk_viol = int(evidence.get("risk_limit_violations") or 0)
    recon_fail = int(evidence.get("reconciliation_failures") or 0)
    dq = int(evidence.get("data_quality_incidents") or 0)
    exec_fail = int(evidence.get("execution_failures") or 0)
    kill_n = int(evidence.get("kill_switch_incidents") or 0)
    turnover = evidence.get("turnover")
    slip = evidence.get("mean_slippage_bps")
    recon_ok = bool(evidence.get("reconciliation_ok", False))

    if duration < pol.min_session_duration_seconds:
        blockers.append(
            f"insufficient_duration:{duration}<{pol.min_session_duration_seconds}"
        )
    if sessions < pol.min_sessions:
        blockers.append(f"insufficient_sessions:{sessions}<{pol.min_sessions}")
    if trades < pol.min_trades:
        blockers.append(f"insufficient_trades:{trades}<{pol.min_trades}")
    if max_dd > pol.max_drawdown:
        blockers.append(f"max_drawdown_violation:{max_dd}>{pol.max_drawdown}")
    if risk_viol > pol.max_risk_limit_violations:
        blockers.append(f"risk_limit_violations:{risk_viol}")
    if recon_fail > pol.max_reconciliation_failures:
        blockers.append(f"reconciliation_failures:{recon_fail}")
    if dq > pol.max_data_quality_incidents:
        blockers.append(f"data_quality_incidents:{dq}")
    if exec_fail > pol.max_execution_failures:
        blockers.append(f"execution_failures:{exec_fail}")
    if kill_n > pol.max_kill_switch_incidents:
        blockers.append(f"kill_switch_incidents:{kill_n}")
    if pol.require_reconciliation_ok and not recon_ok:
        blockers.append("reconciliation_not_ok")
    if pol.max_turnover is not None and turnover is not None:
        if float(turnover) > pol.max_turnover:
            blockers.append(f"turnover_limit:{turnover}>{pol.max_turnover}")
    if pol.max_slippage_bps_mean is not None and slip is not None:
        if float(slip) > pol.max_slippage_bps_mean:
            blockers.append(f"slippage_tolerance:{slip}>{pol.max_slippage_bps_mean}")

    if comparison and pol.require_no_material_divergence:
        if comparison.get("material_divergence"):
            blockers.append("material_backtest_paper_divergence")
        flags = comparison.get("divergence_flags") or []
        for f in flags:
            reasons.append(f"divergence:{f}")

    # Never claim profitability
    if pol.claim_profitability:
        blockers.append("policy_forbids_profitability_claims")
    if evidence.get("claims_profitability"):
        blockers.append("evidence_profitability_claim_forbidden")

    snapshot = {
        "duration_seconds": duration,
        "sessions": sessions,
        "trades": trades,
        "max_drawdown": max_dd,
        "reconciliation_ok": recon_ok,
    }

    if blockers:
        verdict = (
            PaperPolicyVerdict.INSUFFICIENT_EVIDENCE
            if any("insufficient" in b for b in blockers)
            else PaperPolicyVerdict.FAILED
        )
        return PaperPolicyDecision(
            verdict=verdict,
            live_eligibility_candidate=False,
            policy_id=pol.policy_id,
            blockers=blockers,
            reasons=reasons + ["paper_policy_failed"],
            metrics_snapshot=snapshot,
        )

    reasons.append("paper_policy_v1_passed")
    reasons.append("live_trading_remains_disabled")
    return PaperPolicyDecision(
        verdict=PaperPolicyVerdict.PASSED,
        live_eligibility_candidate=True,
        policy_id=pol.policy_id,
        reasons=reasons,
        blockers=[],
        metrics_snapshot=snapshot,
    )
