"""Controlled simulation paper eligibility — separate from research→paper ladder.

Does NOT modify PaperEligibilityGate. DEVELOPMENT_ONLY never becomes
RESEARCH_ELIGIBLE. Controlled paper eligibility may be TRUE for simulation
when all Phase 12 gates pass, including human paper activation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.paper.eligibility import PaperEligibilityGate
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import SessionMode
from quantfund.phase12.activation import PaperActivationRecord, verify_paper_activation_record


KNOWN_COST_MODELS = frozenset({"equity_delivery_v1"})
KNOWN_SLIPPAGE_MODELS = frozenset({"fixed_bps_5", "fixed_bps_0", "fixed_bps_10"})


@dataclass
class ControlledPaperEligibilityDecision:
    paper_eligible: bool
    controlled_paper_eligible: bool
    research_eligibility: str
    research_paper_eligible: bool
    blockers: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    claims: str = "NONE"
    live_trading: str = "DISABLED"
    execution_mode: str = "PAPER"

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_eligible": self.paper_eligible,
            "controlled_paper_eligible": self.controlled_paper_eligible,
            "research_eligibility": self.research_eligibility,
            "research_paper_eligible": self.research_paper_eligible,
            "blockers": list(self.blockers),
            "reasons": list(self.reasons),
            "claims": self.claims,
            "live_trading": self.live_trading,
            "execution_mode": self.execution_mode,
        }


class ControlledSimulationPaperGate:
    """Phase 12 paper gates for controlled simulation (yfinance/fixtures OK)."""

    def evaluate(
        self,
        *,
        research_eligibility: str,
        dataset_provider_configured: bool,
        market_data_available: bool,
        market_data_timestamps_valid: bool,
        stale_data_ok: bool,
        calendar_session_ok: bool,
        strategy_explicitly_enabled: bool,
        strategy_spec_valid: bool,
        risk_config_valid: bool,
        risk_limits_valid: bool,
        kill_switch: KillSwitch,
        paper_execution_adapter_selected: bool,
        live_execution_adapter_selected: bool,
        broker_credentials_available_to_execution: bool,
        reconciliation_clean: bool,
        journal_writable: bool,
        portfolio_restorable: bool,
        deterministic_replay_ok: bool,
        using_research_acceptance_as_authorization: bool,
        activation: PaperActivationRecord | None,
        cost_model_id: str,
        slippage_model_id: str,
        strategy_id: str,
        strategy_version: str,
        # Research ladder (informational; never weakened)
        session_mode_for_research_gate: SessionMode = SessionMode.INFRASTRUCTURE_SANDBOX,
        acceptance_evidence_id: str | None = None,
    ) -> ControlledPaperEligibilityDecision:
        blockers: list[str] = []
        reasons: list[str] = []

        elig = (research_eligibility or "").strip().lower()
        reasons.append(f"research_eligibility={elig}")

        # Always evaluate research→paper ladder for transparency (unchanged)
        research_decision = PaperEligibilityGate().evaluate(
            certified_eligibility=elig,
            session_mode=session_mode_for_research_gate,
            acceptance_evidence_id=acceptance_evidence_id,
        )
        research_paper_eligible = research_decision.paper_eligible
        if elig == "development_only":
            reasons.append("development_only_unchanged_not_research_eligible")

        if not dataset_provider_configured:
            blockers.append("dataset_provider_not_configured")
        if not market_data_available:
            blockers.append("market_data_unavailable")
        if not market_data_timestamps_valid:
            blockers.append("market_data_timestamps_invalid")
        if not stale_data_ok:
            blockers.append("stale_data_detected")
        if not calendar_session_ok:
            blockers.append("calendar_session_invalid")
        if not strategy_explicitly_enabled:
            blockers.append("strategy_not_explicitly_enabled")
        if not strategy_spec_valid:
            blockers.append("strategy_spec_invalid")
        if not risk_config_valid:
            blockers.append("risk_config_invalid")
        if not risk_limits_valid:
            blockers.append("risk_limits_invalid")
        if kill_switch is None:
            blockers.append("kill_switch_missing")
        elif kill_switch.is_triggered:
            blockers.append("kill_switch_triggered")
        if not paper_execution_adapter_selected:
            blockers.append("paper_execution_adapter_not_selected")
        if live_execution_adapter_selected:
            blockers.append("live_execution_adapter_selected")
        if broker_credentials_available_to_execution:
            blockers.append("broker_credentials_must_be_unavailable_to_paper_execution")
        if not reconciliation_clean:
            blockers.append("reconciliation_not_clean")
        if not journal_writable:
            blockers.append("journal_not_writable")
        if not portfolio_restorable:
            blockers.append("portfolio_not_restorable")
        if not deterministic_replay_ok:
            blockers.append("deterministic_replay_failed")
        if using_research_acceptance_as_authorization:
            blockers.append("research_acceptance_cannot_authorize_controlled_paper")
        if cost_model_id not in KNOWN_COST_MODELS:
            blockers.append("unknown_cost_model")
        if slippage_model_id not in KNOWN_SLIPPAGE_MODELS:
            blockers.append("unknown_slippage_model")

        if activation is None:
            blockers.append("missing_paper_activation_record")
        else:
            blockers.extend(
                verify_paper_activation_record(
                    activation,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                )
            )

        controlled = len(blockers) == 0
        if controlled:
            reasons.append("controlled_simulation_paper_gates_passed")
        else:
            reasons.append("controlled_paper_eligible=false")

        return ControlledPaperEligibilityDecision(
            paper_eligible=controlled,
            controlled_paper_eligible=controlled,
            research_eligibility=elig,
            research_paper_eligible=research_paper_eligible,
            blockers=blockers,
            reasons=reasons,
            claims="NONE",
            live_trading="DISABLED",
            execution_mode="PAPER",
        )
