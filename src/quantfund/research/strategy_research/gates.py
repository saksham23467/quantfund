"""Fail-closed gates for controlled Phase 19 strategy research.

Two layers of gating, both fail closed:

1. Research-eligibility PREREQUISITE (dataset-level). Strategy research may only
   begin when the dataset is already certified research-eligible AND the PIT
   universe layer is research-grade. This never re-derives or weakens the
   central gate — it reads the authoritative Phase 18 verdict and the PIT
   universe coverage verdict.
2. Per-candidate DATA-INTEGRITY gate. Even inside an eligible campaign, every
   candidate must run on a point-in-time universe, exchange-grade data, RAW
   execution prices, explicit transaction costs, explicit slippage, realistic
   execution timing, and with no look-ahead / no survivorship bias. Any missing
   guarantee rejects the candidate.

The funnel acceptance thresholds inherit the campaign ``AcceptancePolicy``
defaults and are only ever made *stricter*, never weaker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.research.campaign import AcceptancePolicy
from quantfund.research.strategy_research.record import SplitMetrics


@dataclass(frozen=True)
class PrerequisiteResult:
    research_eligible: bool
    phase18_research_eligible: bool
    pit_universe_research_eligible: bool
    blockers: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_eligible": self.research_eligible,
            "phase18_research_eligible": self.phase18_research_eligible,
            "pit_universe_research_eligible": self.pit_universe_research_eligible,
            "blockers": list(self.blockers),
            "evidence": dict(self.evidence),
        }


def evaluate_prerequisite(
    *,
    phase18_payload: dict[str, Any] | None,
    pit_payload: dict[str, Any] | None,
) -> PrerequisiteResult:
    """Combine authoritative dataset + PIT-universe eligibility. Fails closed.

    A missing verdict is treated as NOT eligible (never assumed True).
    """
    p18 = bool((phase18_payload or {}).get("research_eligible")) if phase18_payload else False
    pit = (
        bool((pit_payload or {}).get("research_eligibility")) if pit_payload else False
    )
    blockers: list[str] = []
    if phase18_payload is None:
        blockers.append("phase18_eligibility_verdict_missing")
    elif not p18:
        stopped = phase18_payload.get("stopped_at_blocker")
        blockers.append(f"phase18_research_eligible=false(stopped_at={stopped})")
    if pit_payload is None:
        blockers.append("pit_universe_coverage_verdict_missing")
    elif not pit:
        blockers.extend(
            f"pit_universe:{b}" for b in (pit_payload.get("blockers") or [])
        )

    eligible = p18 and pit
    return PrerequisiteResult(
        research_eligible=eligible,
        phase18_research_eligible=p18,
        pit_universe_research_eligible=pit,
        blockers=blockers,
        evidence={
            "phase18_stopped_at_blocker": (phase18_payload or {}).get(
                "stopped_at_blocker"
            ),
            "pit_membership_coverage_ratio": (pit_payload or {}).get(
                "membership_coverage_ratio"
            ),
            "pit_unknown_membership_count": (pit_payload or {}).get(
                "unknown_membership_count"
            ),
        },
    )


@dataclass(frozen=True)
class DataIntegrityRequirements:
    """Per-candidate hard requirements. All must be satisfied by the evaluator."""

    point_in_time_universe: bool
    exchange_grade_data: bool
    raw_execution_prices: bool
    transaction_costs_modeled: bool
    slippage_modeled: bool
    realistic_execution_timing: bool
    no_look_ahead: bool
    no_survivorship_bias: bool

    _FIELDS = (
        "point_in_time_universe",
        "exchange_grade_data",
        "raw_execution_prices",
        "transaction_costs_modeled",
        "slippage_modeled",
        "realistic_execution_timing",
        "no_look_ahead",
        "no_survivorship_bias",
    )

    def failures(self) -> list[str]:
        return [f"data_integrity:{name}" for name in self._FIELDS if not getattr(self, name)]

    @property
    def satisfied(self) -> bool:
        return not self.failures()


@dataclass(frozen=True)
class GatePolicy:
    """Funnel thresholds. Inherit AcceptancePolicy; only ever made stricter."""

    min_trades: int = 1
    min_validation_sharpe: float = 0.5
    min_oos_sharpe: float = 0.5
    max_oos_drawdown: float = 0.35
    robustness_min_pass_rate: float = 0.5
    robustness_reject_if_fragile: bool = True
    dsr_min: float = 0.95

    @classmethod
    def from_acceptance_policy(cls, policy: AcceptancePolicy) -> GatePolicy:
        """Derive from campaign policy, taking the STRICTER of the two floors."""
        rob = policy.robustness
        val = policy.validation
        min_val_sharpe = max(0.5, val.min_validation_sharpe or 0.0)
        return cls(
            min_trades=max(1, val.min_trades),
            min_validation_sharpe=min_val_sharpe,
            min_oos_sharpe=min_val_sharpe,
            robustness_min_pass_rate=max(0.5, rob.min_pass_rate),
            robustness_reject_if_fragile=bool(rob.reject_if_fragile),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_trades": self.min_trades,
            "min_validation_sharpe": self.min_validation_sharpe,
            "min_oos_sharpe": self.min_oos_sharpe,
            "max_oos_drawdown": self.max_oos_drawdown,
            "robustness_min_pass_rate": self.robustness_min_pass_rate,
            "robustness_reject_if_fragile": self.robustness_reject_if_fragile,
            "dsr_min": self.dsr_min,
        }


def validation_gate(metrics: SplitMetrics, policy: GatePolicy) -> list[str]:
    reasons: list[str] = []
    if metrics.n_trades < policy.min_trades:
        reasons.append("validation:below_min_trades")
    if not _finite(metrics.sharpe):
        reasons.append("validation:non_finite_sharpe")
    elif metrics.sharpe < policy.min_validation_sharpe:
        reasons.append("validation:sharpe_below_floor")
    return reasons


def oos_gate(metrics: SplitMetrics, policy: GatePolicy) -> list[str]:
    reasons: list[str] = []
    if metrics.n_trades < policy.min_trades:
        reasons.append("oos:below_min_trades")
    if not _finite(metrics.sharpe):
        reasons.append("oos:non_finite_sharpe")
    elif metrics.sharpe < policy.min_oos_sharpe:
        reasons.append("oos:sharpe_below_floor")
    if metrics.max_drawdown > policy.max_oos_drawdown:
        reasons.append("oos:drawdown_exceeds_max")
    return reasons


def robustness_gate(
    pass_rate: float | None, fragile: bool, policy: GatePolicy
) -> list[str]:
    reasons: list[str] = []
    if policy.robustness_reject_if_fragile and fragile:
        reasons.append("robustness:fragile")
    if pass_rate is None:
        reasons.append("robustness:no_pass_rate")
    elif pass_rate < policy.robustness_min_pass_rate:
        reasons.append("robustness:pass_rate_below_floor")
    return reasons


def dsr_gate(deflated_sharpe: float | None, policy: GatePolicy) -> list[str]:
    if deflated_sharpe is None:
        return ["dsr:undefined"]
    if deflated_sharpe < policy.dsr_min:
        return ["dsr:below_floor"]
    return []


def _finite(x: float | None) -> bool:
    return x is not None and x == x and x not in (float("inf"), float("-inf"))
