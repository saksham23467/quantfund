"""Strategy selection report — never invent PAPER_CANDIDATE acceptance."""

from __future__ import annotations

from typing import Any

from quantfund.paper.eligibility import PaperEligibilityGate
from quantfund.paper.models import SessionMode
from quantfund.phase19.selection import PaperCandidate, select_paper_strategy
from quantfund.phase19.strategy_factory import strategy_and_spec_for


def evaluate_strategy_for_phase21(
    *,
    symbol: str = "RELIANCE",
    allow_sandbox: bool = True,
) -> dict[str, Any]:
    """Load existing strategies; report eligibility without weakening gates."""
    candidate, mode = select_paper_strategy(allow_sandbox_demo=allow_sandbox)
    if candidate is None:
        return {
            "strategy_name": None,
            "strategy_hash": None,
            "configuration_hash": None,
            "dataset_config_provenance": None,
            "phase18_eligibility_status": "NONE",
            "PAPER_CANDIDATE": False,
            "reason": "no_strategy_available",
            "mode": "BLOCKED",
            "observation_sandbox": False,
        }

    factory, spec = strategy_and_spec_for(candidate, symbol=symbol)
    meta = factory().metadata()
    from quantfund.phase15.freeze import freeze_session_config

    frozen = freeze_session_config(
        strategy_id=meta.strategy_id,
        strategy_version=meta.strategy_version,
        strategy_params=dict(candidate.parameters),
        strategy_spec=spec.model_dump(mode="json") if hasattr(spec, "model_dump") else dict(spec or {}),
        risk_config={},
        execution_model="paper_next_bar_open",
        campaign_id="phase21",
        dataset_provenance="phase18_artifacts",
        session_config_hash="phase21_preflight",
    )

    gate = PaperEligibilityGate()
    decision = gate.evaluate(
        certified_eligibility="development_only",
        session_mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        campaign_accepted=bool(candidate.research_accepted),
        acceptance_evidence_id=None,
    )
    paper_candidate = bool(
        candidate.research_accepted
        and decision.paper_eligible
        and mode == "PRODUCTION_PAPER_ELIGIBLE"
    )
    reason = (
        "research_accepted_and_paper_eligible"
        if paper_candidate
        else (
            ";".join(decision.blockers)
            if decision.blockers
            else "phase18_accepted_count_zero_or_development_only"
        )
    )

    return {
        "strategy_name": candidate.strategy_family,
        "candidate_id": candidate.candidate_id,
        "strategy_hash": frozen.strategy_hash,
        "configuration_hash": frozen.freeze_token,
        "parameter_hash": frozen.parameters_hash,
        "dataset_config_provenance": {
            "source": candidate.source,
            "research_accepted": candidate.research_accepted,
            "rank": candidate.rank,
            "mean_validation_sharpe": candidate.mean_validation_sharpe,
        },
        "phase18_eligibility_status": (
            "ACCEPTED" if candidate.research_accepted else "NOT_ACCEPTED"
        ),
        "PAPER_CANDIDATE": paper_candidate,
        "reason": reason,
        "mode": mode if paper_candidate else "OBSERVATION_PAPER_SANDBOX",
        "observation_sandbox": not paper_candidate,
        "paper_eligibility": decision.to_dict(),
        "candidate": candidate.to_dict(),
    }


__all__ = ["evaluate_strategy_for_phase21", "PaperCandidate"]
