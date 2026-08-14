"""Research → paper eligibility gate.

Campaign acceptance alone never implies paper eligibility.
DEVELOPMENT_ONLY always yields paper_eligible=false.

Phase 10: PRODUCTION sessions require full research-acceptance evidence
(sealed TEST, robustness, walk-forward, DSR/trials, no leakage, risk/exec
config, operator-controlled session). Sandbox remains non-eligible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.paper.models import SessionMode

if TYPE_CHECKING:
    from quantfund.research.acceptance_record import StrategyAcceptanceRecord


@dataclass
class PaperEligibilityDecision:
    paper_eligible: bool
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    certified_eligibility: str | None = None
    mode: SessionMode = SessionMode.INFRASTRUCTURE_SANDBOX

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_eligible": self.paper_eligible,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "certified_eligibility": self.certified_eligibility,
            "mode": self.mode.value,
        }


class PaperEligibilityGate:
    """Explicit gate: research artifacts + eligibility contracts → paper_eligible."""

    def __init__(
        self,
        eligibility_checker: ResearchEligibilityChecker | None = None,
    ) -> None:
        self.checker = eligibility_checker or ResearchEligibilityChecker()

    def evaluate(
        self,
        *,
        certified_eligibility: str,
        session_mode: SessionMode = SessionMode.INFRASTRUCTURE_SANDBOX,
        acceptance_evidence_id: str | None = None,
        campaign_accepted: bool = False,
        facts: DatasetCertificationFacts | None = None,
        strategy_spec_hash: str | None = None,
        accepted_strategy_spec_hash: str | None = None,
        acceptance_record: StrategyAcceptanceRecord | None = None,
        sealed_test_ok: bool = False,
        robustness_ok: bool = False,
        walkforward_ok: bool = False,
        dsr_trial_accounting_ok: bool = False,
        no_leakage: bool = False,
        no_unknown_membership_traded: bool = False,
        risk_config_valid: bool = False,
        execution_config_valid: bool = False,
        operator_approved_paper_session: bool = False,
    ) -> PaperEligibilityDecision:
        blockers: list[str] = []
        reasons: list[str] = []

        elig = (certified_eligibility or "").strip().lower()
        if elig == "development_only":
            blockers.append("development_only_dataset_cannot_be_paper_eligible")

        if elig not in {"research_eligible", "production_candidate"}:
            blockers.append(f"certified_eligibility={elig} insufficient for paper")

        if facts is not None:
            decision = self.checker.evaluate(facts)
            if decision.level == EligibilityLevel.DEVELOPMENT_ONLY:
                blockers.append("ResearchEligibilityChecker=development_only")
            if decision.level not in {
                EligibilityLevel.RESEARCH_ELIGIBLE,
                EligibilityLevel.PRODUCTION_CANDIDATE,
            }:
                blockers.append(f"live_checker_level={decision.level.value}")

        # Campaign acceptance alone is never sufficient
        if campaign_accepted and not acceptance_evidence_id:
            reasons.append(
                "campaign_accepted_without_paper_authorization_evidence_ignored"
            )
        if not acceptance_evidence_id:
            blockers.append("missing_acceptance_evidence_id")

        if acceptance_record is not None:
            from quantfund.research.acceptance_record import verify_acceptance_record

            rec_blockers = verify_acceptance_record(acceptance_record)
            blockers.extend(rec_blockers)
            if acceptance_record.acceptance_evidence_id != acceptance_evidence_id:
                blockers.append("acceptance_evidence_id_record_mismatch")
            # Prefer record flags when provided
            sealed_test_ok = sealed_test_ok or acceptance_record.sealed_test_ok
            robustness_ok = robustness_ok or acceptance_record.robustness_ok
            walkforward_ok = walkforward_ok or acceptance_record.walkforward_ok
            dsr_trial_accounting_ok = (
                dsr_trial_accounting_ok or acceptance_record.dsr_trial_accounting_ok
            )
            no_leakage = no_leakage or acceptance_record.no_leakage
            no_unknown_membership_traded = (
                no_unknown_membership_traded
                or acceptance_record.no_unknown_membership_traded
            )

        if (
            strategy_spec_hash
            and accepted_strategy_spec_hash
            and strategy_spec_hash != accepted_strategy_spec_hash
        ):
            blockers.append("strategy_spec_hash_mismatch")

        # Infrastructure sandbox never claims paper_eligible=true
        if session_mode == SessionMode.INFRASTRUCTURE_SANDBOX:
            blockers.append("infrastructure_sandbox_cannot_be_paper_eligible")
            reasons.append("sandbox_may_exercise_kernel_without_paper_eligibility")

        # Phase 10 full authorization ladder for PRODUCTION paper
        if session_mode == SessionMode.PRODUCTION:
            if not sealed_test_ok:
                blockers.append("sealed_test_required")
            if not robustness_ok:
                blockers.append("robustness_required")
            if not walkforward_ok:
                blockers.append("walkforward_requirements_unsatisfied")
            if not dsr_trial_accounting_ok:
                blockers.append("dsr_trial_accounting_invalid")
            if not no_leakage:
                blockers.append("leakage_detected_or_unverified")
            if not no_unknown_membership_traded:
                blockers.append("unknown_membership_traded_or_unverified")
            if not risk_config_valid:
                blockers.append("invalid_risk_configuration")
            if not execution_config_valid:
                blockers.append("invalid_execution_configuration")
            if not operator_approved_paper_session:
                blockers.append("operator_paper_session_required")

        paper_eligible = len(blockers) == 0
        # Defense in depth: sandbox / development_only hard false
        if session_mode == SessionMode.INFRASTRUCTURE_SANDBOX:
            paper_eligible = False
        if elig == "development_only":
            paper_eligible = False

        if paper_eligible:
            reasons.append("all_paper_eligibility_gates_passed")
        else:
            reasons.append("paper_eligible=false")

        return PaperEligibilityDecision(
            paper_eligible=paper_eligible,
            reasons=reasons,
            blockers=blockers,
            certified_eligibility=elig,
            mode=session_mode,
        )
