"""Campaign acceptance policy — evaluator-owned; never called by generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.research.campaign import AcceptancePolicy, CampaignPurpose
from quantfund.research.campaign_state import CandidateState
from quantfund.research.candidate_pool import CandidateRecord
from quantfund.research.test_seal import CampaignTestSeal


@dataclass
class AcceptanceDecision:
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "notes": list(self.notes),
        }


class CampaignAcceptancePolicy:
    """Hard gates for accepted_research_candidate."""

    def __init__(self, policy: AcceptancePolicy) -> None:
        self.policy = policy

    def decide(
        self,
        *,
        candidate: CandidateRecord,
        purpose: CampaignPurpose,
        certified_eligibility: str,
        seal: CampaignTestSeal,
        robustness_pass_rate: float | None,
        robustness_fragile: bool,
        walkforward_enabled: bool,
        walkforward_stats: dict[str, Any] | None,
        score_accepted: bool | None,
        score_rejection_reasons: list[str] | None,
        trial_counts: dict[str, int],
        unknown_membership_traded: bool = False,
        feature_leakage: bool = False,
    ) -> AcceptanceDecision:
        reasons: list[str] = []
        notes: list[str] = []

        if purpose == CampaignPurpose.EXPLORATORY_DEVELOPMENT:
            reasons.append("exploratory_development_cannot_accept")
        if certified_eligibility == "development_only":
            reasons.append("development_only_dataset_cannot_be_accepted")
        if (
            self.policy.require_research_eligible_dataset
            and certified_eligibility
            not in {"research_eligible", "production_candidate"}
        ):
            reasons.append(
                f"dataset_eligibility={certified_eligibility} insufficient"
            )

        if seal.contamination_events:
            reasons.append("campaign_contaminated")
        if self.policy.require_sealed_test and not seal.sealed:
            reasons.append("campaign_not_sealed")
        if candidate.state not in {
            CandidateState.TEST_EVALUATED,
            CandidateState.SEALED,
            CandidateState.ACCEPTED,
            CandidateState.REJECTED,
        }:
            # Must have completed TEST for acceptance under require_sealed_test
            pass
        if self.policy.require_sealed_test:
            if candidate.test_evaluations != 1:
                reasons.append(
                    f"test_evaluations={candidate.test_evaluations} "
                    f"(require exactly 1)"
                )
            if candidate.candidate_id not in seal.test_evaluation_log:
                reasons.append("candidate_missing_from_test_log")

        if candidate.test_evaluations > self.policy.max_test_evaluations_per_candidate:
            reasons.append("test_evaluated_more_than_once")

        if unknown_membership_traded:
            reasons.append("unknown_membership_traded")
        if feature_leakage:
            reasons.append("feature_leakage")

        rob = self.policy.robustness
        if robustness_fragile and rob.reject_if_fragile:
            reasons.append("robustness_fragile")
        if (
            robustness_pass_rate is not None
            and robustness_pass_rate < rob.min_pass_rate
        ):
            reasons.append(
                f"robustness_pass_rate={robustness_pass_rate} "
                f"< {rob.min_pass_rate}"
            )

        if walkforward_enabled:
            wf_pol = self.policy.walkforward
            stats = walkforward_stats or {}
            frac = stats.get("fraction_positive_windows")
            if frac is not None and frac < wf_pol.min_fraction_positive_windows:
                reasons.append(
                    f"wf_fraction_positive={frac} "
                    f"< {wf_pol.min_fraction_positive_windows}"
                )
            med = stats.get("median_window_sharpe")
            if (
                wf_pol.min_median_window_sharpe is not None
                and med is not None
                and med < wf_pol.min_median_window_sharpe
            ):
                reasons.append("wf_median_sharpe_below_floor")
        else:
            notes.append("walkforward_disabled")

        if score_accepted is False:
            reasons.extend(score_rejection_reasons or ["score_rejected"])

        # Score cannot override hard rejects — already accumulating reasons
        if trial_counts.get("n_experiments", 0) < 0:
            reasons.append("inconsistent_trial_accounting")

        accepted = len(reasons) == 0
        # Absolute ban: development_only / exploratory never accepted
        if certified_eligibility == "development_only":
            accepted = False
        if purpose == CampaignPurpose.EXPLORATORY_DEVELOPMENT:
            accepted = False

        return AcceptanceDecision(accepted=accepted, reasons=reasons, notes=notes)
