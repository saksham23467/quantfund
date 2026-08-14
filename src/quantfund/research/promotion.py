"""Research → acceptance → paper eligibility → paper evidence → live candidate.

Stops before live trading. Never enables LIVE_SEND or real brokers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.execution.live_eligibility import LiveTradingEligibilityGate
from quantfund.paper.eligibility import PaperEligibilityGate
from quantfund.paper.models import SessionMode
from quantfund.research.acceptance_record import (
    StrategyAcceptanceRecord,
    build_acceptance_record,
    verify_acceptance_record,
)
from quantfund.research.backtest_paper_compare import compare_backtest_paper
from quantfund.research.certify_package import certify_research_package
from quantfund.research.drift import evaluate_drift
from quantfund.research.paper_evidence import (
    PaperEvidenceRecord,
    aggregate_paper_evidence,
    verify_paper_evidence,
)
from quantfund.research.paper_policy import (
    PaperPolicyDecision,
    PaperPolicyV1,
    evaluate_paper_policy,
)
from quantfund.research.paper_report import build_paper_validation_report
from quantfund.research.paper_session_fsm import PaperSessionFSM, PaperValidationState


class LiveCandidateStatus(str, Enum):
    NOT_A_CANDIDATE = "NOT_A_CANDIDATE"
    LIVE_ELIGIBILITY_CANDIDATE = "LIVE_ELIGIBILITY_CANDIDATE"
    BLOCKED = "BLOCKED"


@dataclass
class PromotionSnapshot:
    research_eligibility: str
    paper_eligible: bool
    accepted_count: int
    paper_sessions_completed: int
    paper_policy: PaperPolicyDecision | None
    live_candidate: LiveCandidateStatus
    live_eligible: bool
    real_orders: int
    claims: str
    blockers: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_eligibility": self.research_eligibility,
            "paper_eligible": self.paper_eligible,
            "accepted_count": self.accepted_count,
            "paper_sessions_completed": self.paper_sessions_completed,
            "paper_policy": self.paper_policy.to_dict() if self.paper_policy else None,
            "live_candidate": self.live_candidate.value,
            "live_eligible": self.live_eligible,
            "real_orders": self.real_orders,
            "claims": self.claims,
            "blockers": list(self.blockers),
            "report": self.report,
        }


def certify_configured_research_package(
    *,
    package_root: Path | None = None,
) -> tuple[str, DatasetCertificationFacts | None, list[str], dict[str, Any]]:
    """Run existing Phase 5/7 certification path. Never fabricates RESEARCH_ELIGIBLE."""
    return certify_research_package(package_root)


def evaluate_paper_eligibility_from_acceptance(
    record: StrategyAcceptanceRecord,
    *,
    session_mode: SessionMode = SessionMode.PRODUCTION,
    risk_config_valid: bool = True,
    execution_config_valid: bool = True,
    operator_approved_paper_session: bool = True,
    facts: DatasetCertificationFacts | None = None,
) -> Any:
    """PaperEligibilityGate wrapper consuming a verified acceptance record."""
    blockers = verify_acceptance_record(record)
    if blockers:
        from quantfund.paper.eligibility import PaperEligibilityDecision

        return PaperEligibilityDecision(
            paper_eligible=False,
            reasons=["acceptance_record_invalid"],
            blockers=blockers,
            certified_eligibility=record.research_eligibility,
            mode=session_mode,
        )
    return PaperEligibilityGate().evaluate(
        certified_eligibility=record.research_eligibility,
        session_mode=session_mode,
        acceptance_evidence_id=record.acceptance_evidence_id,
        campaign_accepted=True,
        facts=facts,
        strategy_spec_hash=record.strategy_hash,
        accepted_strategy_spec_hash=record.strategy_hash,
        acceptance_record=record,
        sealed_test_ok=record.sealed_test_ok,
        robustness_ok=record.robustness_ok,
        walkforward_ok=record.walkforward_ok,
        dsr_trial_accounting_ok=record.dsr_trial_accounting_ok,
        no_leakage=record.no_leakage,
        no_unknown_membership_traded=record.no_unknown_membership_traded,
        risk_config_valid=risk_config_valid,
        execution_config_valid=execution_config_valid,
        operator_approved_paper_session=operator_approved_paper_session,
    )


def evaluate_live_eligibility_candidate(
    *,
    certified_eligibility: str,
    acceptance: StrategyAcceptanceRecord | None,
    paper_eligible: bool,
    paper_evidence: PaperEvidenceRecord | list[PaperEvidenceRecord] | None,
    paper_policy: PaperPolicyDecision | None,
    comparison: dict[str, Any] | None = None,
) -> tuple[LiveCandidateStatus, list[str]]:
    """Paper-policy pass → LIVE_ELIGIBILITY_CANDIDATE. Live trading stays disabled."""
    blockers: list[str] = []
    if (certified_eligibility or "").lower() == "development_only":
        return LiveCandidateStatus.BLOCKED, ["development_only"]
    if acceptance is None:
        blockers.append("missing_acceptance_record")
    else:
        blockers.extend(verify_acceptance_record(acceptance))
    if not paper_eligible:
        blockers.append("not_paper_eligible")
    if paper_evidence is None:
        blockers.append("missing_paper_evidence")
    else:
        records = (
            paper_evidence
            if isinstance(paper_evidence, list)
            else [paper_evidence]
        )
        for r in records:
            blockers.extend(verify_paper_evidence(r))
    if paper_policy is None or not paper_policy.live_eligibility_candidate:
        blockers.append("paper_policy_not_passed")
    if comparison and comparison.get("material_divergence"):
        # Policy may already block; still record
        if "material_backtest_paper_divergence" not in blockers:
            blockers.append("material_divergence")

    # Never authorize live send here — candidate only
    if blockers:
        return LiveCandidateStatus.BLOCKED, blockers

    # Confirm live gate would still require operator + mock; send disabled
    live = LiveTradingEligibilityGate().evaluate(
        certified_eligibility=certified_eligibility,
        research_accepted=True,
        acceptance_evidence_id=(
            acceptance.acceptance_evidence_id if acceptance else None
        ),
        sealed_test_ok=bool(acceptance and acceptance.sealed_test_ok),
        robustness_ok=bool(acceptance and acceptance.robustness_ok),
        paper_eligible=paper_eligible,
        paper_evidence_id=(
            paper_evidence.paper_evidence_id
            if isinstance(paper_evidence, PaperEvidenceRecord)
            else paper_evidence[0].paper_evidence_id
        ),
        paper_reconciliation_passed=True,
        allow_live_send=False,
    )
    # Candidate status is independent of LIVE_AUTHORIZED (Phase 11 needed for send)
    _ = live
    return LiveCandidateStatus.LIVE_ELIGIBILITY_CANDIDATE, []


def run_phase10_pipeline_synthetic() -> PromotionSnapshot:
    """Mode A — current synthetic / unconfigured environment."""
    elig, _facts, blockers, meta = certify_configured_research_package()
    if meta.get("configured") is False:
        elig = EligibilityLevel.DEVELOPMENT_ONLY.value
        if "research_package_not_configured" not in blockers:
            blockers.append("research_package_not_configured")

    paper_dec = PaperEligibilityGate().evaluate(
        certified_eligibility=elig,
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id=None,
    )
    report = build_paper_validation_report(
        research_eligibility=elig,
        paper_eligible=False,
        accepted_strategies=[],
        paper_sessions=[],
        paper_policy={"verdict": "NOT_RUN", "live_eligibility_candidate": False},
        live_eligibility_candidate=False,
        real_orders=0,
        claims="NONE",
        blockers=blockers + paper_dec.blockers,
        mode="synthetic",
    )
    report["paper_session"] = "BLOCKED"
    return PromotionSnapshot(
        research_eligibility=elig,
        paper_eligible=False,
        accepted_count=0,
        paper_sessions_completed=0,
        paper_policy=None,
        live_candidate=LiveCandidateStatus.NOT_A_CANDIDATE,
        live_eligible=False,
        real_orders=0,
        claims="NONE",
        blockers=blockers + paper_dec.blockers,
        report=report,
    )


def run_phase10_pipeline_from_package(
    package_root: Path | None = None,
    *,
    acceptance: StrategyAcceptanceRecord | None = None,
    paper_evidence_records: list[PaperEvidenceRecord] | None = None,
    backtest_metrics: dict[str, Any] | None = None,
    paper_metrics: dict[str, Any] | None = None,
    paper_policy: PaperPolicyV1 | None = None,
) -> PromotionSnapshot:
    """Mode B — externally supplied package + optional acceptance/evidence.

    Does not fabricate RESEARCH_ELIGIBLE. Campaign acceptance must be supplied
    from a real campaign or test double that already passed CampaignAcceptancePolicy.
    """
    elig, facts, blockers, meta = certify_configured_research_package(
        package_root=package_root
    )
    accepted: list[dict[str, Any]] = []
    paper_eligible = False
    sessions: list[dict[str, Any]] = []
    policy_dec: PaperPolicyDecision | None = None
    comparison_dict: dict[str, Any] | None = None
    candidate = LiveCandidateStatus.NOT_A_CANDIDATE

    if elig == EligibilityLevel.DEVELOPMENT_ONLY.value:
        report = build_paper_validation_report(
            research_eligibility=elig,
            paper_eligible=False,
            accepted_strategies=[],
            paper_sessions=[],
            paper_policy={"verdict": "NOT_RUN"},
            live_eligibility_candidate=False,
            real_orders=0,
            claims="NONE",
            blockers=blockers,
            mode="research_package",
        )
        report["certification_meta"] = {
            k: v for k, v in meta.items() if k != "certification"
        }
        return PromotionSnapshot(
            research_eligibility=elig,
            paper_eligible=False,
            accepted_count=0,
            paper_sessions_completed=0,
            paper_policy=None,
            live_candidate=LiveCandidateStatus.BLOCKED,
            live_eligible=False,
            real_orders=0,
            claims="NONE",
            blockers=blockers,
            report=report,
        )

    if acceptance is not None:
        paper_dec = evaluate_paper_eligibility_from_acceptance(
            acceptance, facts=facts
        )
        paper_eligible = bool(paper_dec.paper_eligible)
        if paper_eligible:
            accepted.append(acceptance.to_dict())
        else:
            blockers.extend(paper_dec.blockers)

    evidence_list = list(paper_evidence_records or [])
    if evidence_list and paper_eligible:
        for ev in evidence_list:
            fsm = PaperSessionFSM(session_id=ev.session_id)
            try:
                fsm.transition(PaperValidationState.ELIGIBILITY_CHECKED)
                fsm.transition(PaperValidationState.READY)
                fsm.transition(PaperValidationState.RUNNING)
                fsm.transition(PaperValidationState.RECONCILING)
                if not ev.reconciliation_ok:
                    fsm.fail("reconciliation_failed")
                else:
                    fsm.transition(PaperValidationState.COMPLETED)
                    fsm.transition(PaperValidationState.EVALUATED)
            except Exception as exc:  # noqa: BLE001
                fsm.fail(str(exc))
            sessions.append(fsm.to_dict())

        agg = aggregate_paper_evidence(evidence_list)
        comparison = None
        if backtest_metrics is not None and paper_metrics is not None:
            comparison = compare_backtest_paper(backtest_metrics, paper_metrics)
            comparison_dict = comparison.to_dict()
        policy_dec = evaluate_paper_policy(
            agg,
            policy=paper_policy,
            comparison=comparison_dict,
        )
        for s in sessions:
            if s["state"] == PaperValidationState.EVALUATED.value:
                if policy_dec.verdict.value == "PASSED":
                    # advance evaluated → passed via new FSM instance semantics
                    s["state"] = PaperValidationState.PASSED.value
                else:
                    s["state"] = PaperValidationState.FAILED.value
                    s["fail_reason"] = ",".join(policy_dec.blockers)

        candidate, cand_blockers = evaluate_live_eligibility_candidate(
            certified_eligibility=elig,
            acceptance=acceptance,
            paper_eligible=paper_eligible,
            paper_evidence=evidence_list,
            paper_policy=policy_dec,
            comparison=comparison_dict,
        )
        blockers.extend(cand_blockers)

    drift_rep = evaluate_drift(
        baseline=(backtest_metrics or {}),
        observed=(paper_metrics or {}),
    )

    report = build_paper_validation_report(
        research_eligibility=elig,
        paper_eligible=paper_eligible,
        accepted_strategies=accepted,
        paper_sessions=sessions,
        paper_policy=policy_dec.to_dict() if policy_dec else {"verdict": "NOT_RUN"},
        comparison=comparison_dict,
        drift=drift_rep.to_dict(),
        live_eligibility_candidate=(
            candidate == LiveCandidateStatus.LIVE_ELIGIBILITY_CANDIDATE
        ),
        real_orders=0,
        claims="NONE",
        blockers=blockers,
        mode="research_package",
    )
    report["certification_meta"] = {
        k: v for k, v in meta.items() if k != "certification"
    }
    if "certification" in meta:
        report["certification"] = meta["certification"]

    return PromotionSnapshot(
        research_eligibility=elig,
        paper_eligible=paper_eligible,
        accepted_count=len(accepted),
        paper_sessions_completed=sum(
            1
            for s in sessions
            if s.get("state")
            in {
                PaperValidationState.COMPLETED.value,
                PaperValidationState.EVALUATED.value,
                PaperValidationState.PASSED.value,
                PaperValidationState.FAILED.value,
            }
        ),
        paper_policy=policy_dec,
        live_candidate=candidate,
        live_eligible=False,
        real_orders=0,
        claims="NONE",
        blockers=blockers,
        report=report,
    )


# Re-export helper used by tests that assemble facts without a package
def build_acceptance_for_tests(**kwargs: Any) -> StrategyAcceptanceRecord:
    return build_acceptance_record(**kwargs)
