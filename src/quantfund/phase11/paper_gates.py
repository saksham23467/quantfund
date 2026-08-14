"""Phase 11 paper certification gates — additive; never weakens PaperEligibilityGate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.paper.eligibility import PaperEligibilityDecision, PaperEligibilityGate
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import SessionMode
from quantfund.phase11.connectivity_status import (
    BrokerConnectivityStatus,
    assert_not_live,
)


@dataclass
class Phase11PaperGateDecision:
    paper_eligible: bool
    research_eligibility: str
    connectivity: BrokerConnectivityStatus
    blockers: list[str] = field(default_factory=list)
    base: PaperEligibilityDecision | None = None
    execution_mode: str = "PAPER"
    live_trading: str = "DISABLED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_eligible": self.paper_eligible,
            "research_eligibility": self.research_eligibility,
            "connectivity": self.connectivity.value,
            "blockers": list(self.blockers),
            "execution_mode": self.execution_mode,
            "live_trading": self.live_trading,
            "base": self.base.to_dict() if self.base else None,
        }


@dataclass
class Phase11PaperCertificationGate:
    """Compose PaperEligibilityGate + operational Phase 11 checks."""

    base_gate: PaperEligibilityGate | None = None

    def evaluate(
        self,
        *,
        certified_eligibility: str,
        connectivity: BrokerConnectivityStatus,
        kill_switch: KillSwitch,
        reconciliation_clean: bool,
        strategy_explicitly_enabled: bool,
        paper_mode_explicit: bool = True,
        live_activation_present: bool = False,
        broker_account_known: bool = False,
        session_mode: SessionMode = SessionMode.INFRASTRUCTURE_SANDBOX,
        **base_kwargs: Any,
    ) -> Phase11PaperGateDecision:
        assert_not_live(connectivity)
        blockers: list[str] = []
        gate = self.base_gate or PaperEligibilityGate()
        base = gate.evaluate(
            certified_eligibility=certified_eligibility,
            session_mode=session_mode,
            **base_kwargs,
        )
        blockers.extend(base.blockers)

        if not paper_mode_explicit:
            blockers.append("paper_mode_not_explicit")
        if connectivity == BrokerConnectivityStatus.LIVE:
            blockers.append("live_connectivity_forbidden_in_phase11")
        if kill_switch.is_triggered:
            blockers.append("kill_switch_triggered")
        # Kill switch must be functional (armed object present)
        if kill_switch is None:
            blockers.append("kill_switch_missing")
        if not reconciliation_clean:
            blockers.append("reconciliation_not_clean")
        if not strategy_explicitly_enabled:
            blockers.append("strategy_not_explicitly_enabled")
        if live_activation_present:
            blockers.append("live_activation_contamination")
        if connectivity == BrokerConnectivityStatus.CONNECTED_READ_ONLY and not broker_account_known:
            blockers.append("broker_account_state_unknown")
        if connectivity == BrokerConnectivityStatus.SIMULATED:
            # Simulated is fine for CI machinery but does not grant paper_eligible
            # unless base gate already passed (it won't on DEVELOPMENT_ONLY)
            pass

        paper_eligible = base.paper_eligible and not blockers
        # Never promote DEVELOPMENT_ONLY
        elig = (certified_eligibility or "").strip().lower()
        if elig == "development_only":
            paper_eligible = False
            if "development_only_dataset_cannot_be_paper_eligible" not in blockers:
                blockers.append("development_only_dataset_cannot_be_paper_eligible")

        return Phase11PaperGateDecision(
            paper_eligible=paper_eligible,
            research_eligibility=elig,
            connectivity=connectivity,
            blockers=blockers,
            base=base,
        )
