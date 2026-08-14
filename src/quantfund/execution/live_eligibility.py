"""LiveTradingEligibilityGate — research ≠ paper ≠ live authorization."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel


class LiveAuthorization(str, Enum):
    LIVE_AUTHORIZED = "LIVE_AUTHORIZED"
    LIVE_BLOCKED = "LIVE_BLOCKED"


@dataclass
class LiveEligibilityDecision:
    authorization: LiveAuthorization
    live_eligible: bool
    blockers: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    certified_eligibility: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization": self.authorization.value,
            "live_eligible": self.live_eligible,
            "blockers": list(self.blockers),
            "reasons": list(self.reasons),
            "certified_eligibility": self.certified_eligibility,
        }


class LiveTradingEligibilityGate:
    """Separate ladder: RESEARCH → PAPER_EVIDENCE → LIVE_ELIGIBLE → (operator later)."""

    def __init__(
        self,
        eligibility_checker: ResearchEligibilityChecker | None = None,
    ) -> None:
        self.checker = eligibility_checker or ResearchEligibilityChecker()

    def evaluate(
        self,
        *,
        certified_eligibility: str,
        research_accepted: bool = False,
        acceptance_evidence_id: str | None = None,
        sealed_test_ok: bool = False,
        robustness_ok: bool = False,
        paper_eligible: bool = False,
        paper_evidence_id: str | None = None,
        paper_reconciliation_passed: bool = False,
        broker_adapter_id: str = "mock",
        risk_config_present: bool = True,
        kill_switch_ready: bool = True,
        facts: DatasetCertificationFacts | None = None,
        allow_live_send: bool = False,  # Phase 9 v1: must stay False
    ) -> LiveEligibilityDecision:
        blockers: list[str] = []
        reasons: list[str] = []
        elig = (certified_eligibility or "").strip().lower()

        # RESEARCH_ELIGIBLE rung
        if elig == "development_only":
            blockers.append("development_only_cannot_be_live_eligible")
        if elig not in {"research_eligible", "production_candidate"}:
            blockers.append(f"certified_eligibility={elig} insufficient for live")

        if facts is not None:
            d = self.checker.evaluate(facts)
            if d.level == EligibilityLevel.DEVELOPMENT_ONLY:
                blockers.append("ResearchEligibilityChecker=development_only")
            if d.level not in {
                EligibilityLevel.RESEARCH_ELIGIBLE,
                EligibilityLevel.PRODUCTION_CANDIDATE,
            }:
                blockers.append(f"checker_level={d.level.value}")

        if not research_accepted:
            blockers.append("research_not_accepted")
        if not acceptance_evidence_id:
            blockers.append("missing_acceptance_evidence_id")
        if research_accepted and not acceptance_evidence_id:
            reasons.append("campaign_acceptance_alone_insufficient")
        if not sealed_test_ok:
            blockers.append("sealed_test_required")
        if not robustness_ok:
            blockers.append("robustness_required")

        # PAPER_EVIDENCE rung
        if not paper_eligible:
            blockers.append("paper_eligible_required")
        if not paper_evidence_id:
            blockers.append("missing_paper_evidence_id")
        if not paper_reconciliation_passed:
            blockers.append("paper_reconciliation_not_passed")
        if paper_eligible and not paper_evidence_id:
            reasons.append("paper_eligibility_alone_insufficient")

        # Broker / risk readiness
        if broker_adapter_id not in {"mock", "mock_broker", "MockBrokerAdapter"}:
            blockers.append("real_broker_forbidden_in_phase9")
        if not risk_config_present:
            blockers.append("risk_config_required")
        if not kill_switch_ready:
            blockers.append("kill_switch_not_ready")

        # Phase 9 v1: never authorize real send
        if allow_live_send:
            blockers.append("live_send_disabled_in_phase9_v1")

        live_eligible = len(blockers) == 0
        # Hard safety: development_only always false
        if elig == "development_only":
            live_eligible = False

        auth = (
            LiveAuthorization.LIVE_AUTHORIZED
            if live_eligible
            else LiveAuthorization.LIVE_BLOCKED
        )
        if not live_eligible:
            reasons.append("LIVE_BLOCKED")
        else:
            reasons.append("all_live_eligibility_rungs_passed")

        return LiveEligibilityDecision(
            authorization=auth,
            live_eligible=live_eligible,
            blockers=blockers,
            reasons=reasons,
            certified_eligibility=elig,
        )
