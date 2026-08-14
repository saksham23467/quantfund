"""Immutable StrategyAcceptanceRecord — evaluator-owned acceptance evidence.

Strategies must never declare themselves accepted. Acceptance is reproducible
from campaign / experiment artifacts via deterministic hashing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantfund.data.ingest.checksums import hash_json
from quantfund.paper.models import state_hash


ACCEPTANCE_POLICY_VERSION = "acceptance_policy_v1"
ACCEPTANCE_RECORD_SCHEMA = "strategy_acceptance_record_v1"


class StrategyAcceptanceRecord(BaseModel):
    """Immutable acceptance evidence artifact (Phase 10)."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = ACCEPTANCE_RECORD_SCHEMA
    acceptance_evidence_id: str
    strategy_id: str
    strategy_version: str
    strategy_hash: str | None = None
    experiment_id: str | None = None
    campaign_id: str
    dataset_id: str
    dataset_version: str
    config_hash: str
    selection_criterion: str
    validation_metrics: dict[str, Any] = Field(default_factory=dict)
    walkforward_metrics: dict[str, Any] = Field(default_factory=dict)
    robustness_summary: dict[str, Any] = Field(default_factory=dict)
    dsr: float | None = None
    n_trials: int = 0
    test_metrics: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None
    acceptance_policy_version: str = ACCEPTANCE_POLICY_VERSION
    research_eligibility: str
    sealed_test_ok: bool = False
    robustness_ok: bool = False
    walkforward_ok: bool = False
    dsr_trial_accounting_ok: bool = False
    no_leakage: bool = True
    no_unknown_membership_traded: bool = True
    accepted_at: datetime
    artifact_digest: str
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("research_eligibility")
    @classmethod
    def eligibility_normalized(cls, v: str) -> str:
        return (v or "").strip().lower()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def is_development_blocked(self) -> bool:
        return self.research_eligibility == "development_only"


def _payload_for_digest(payload: dict[str, Any]) -> dict[str, Any]:
    """Fields that feed artifact_digest (excludes digest itself and accepted_at)."""
    skip = {"artifact_digest", "accepted_at", "extras"}
    return {k: v for k, v in payload.items() if k not in skip}


def make_acceptance_evidence_id(
    *,
    campaign_id: str,
    strategy_id: str,
    strategy_version: str,
    config_hash: str,
    dataset_id: str,
    dataset_version: str,
) -> str:
    return hash_json(
        {
            "campaign_id": campaign_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "config_hash": config_hash,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
        }
    )[:32]


def build_acceptance_record(
    *,
    campaign_id: str,
    strategy_id: str,
    strategy_version: str,
    dataset_id: str,
    dataset_version: str,
    config_hash: str,
    selection_criterion: str,
    research_eligibility: str,
    experiment_id: str | None = None,
    strategy_hash: str | None = None,
    validation_metrics: dict[str, Any] | None = None,
    walkforward_metrics: dict[str, Any] | None = None,
    robustness_summary: dict[str, Any] | None = None,
    dsr: float | None = None,
    n_trials: int = 0,
    test_metrics: dict[str, Any] | None = None,
    score: float | None = None,
    sealed_test_ok: bool = False,
    robustness_ok: bool = False,
    walkforward_ok: bool = False,
    dsr_trial_accounting_ok: bool = False,
    no_leakage: bool = True,
    no_unknown_membership_traded: bool = True,
    acceptance_policy_version: str = ACCEPTANCE_POLICY_VERSION,
    accepted_at: datetime | None = None,
    extras: dict[str, Any] | None = None,
) -> StrategyAcceptanceRecord:
    """Build an immutable acceptance record. Fail closed on development_only."""
    elig = (research_eligibility or "").strip().lower()
    if elig == "development_only":
        raise ValueError(
            "cannot create StrategyAcceptanceRecord for development_only dataset"
        )
    if elig not in {"research_eligible", "production_candidate"}:
        raise ValueError(
            f"cannot create StrategyAcceptanceRecord for eligibility={elig}"
        )
    if not sealed_test_ok:
        raise ValueError("acceptance requires sealed_test_ok=True")
    if not robustness_ok:
        raise ValueError("acceptance requires robustness_ok=True")

    evidence_id = make_acceptance_evidence_id(
        campaign_id=campaign_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        config_hash=config_hash,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
    )
    provisional = {
        "schema_version": ACCEPTANCE_RECORD_SCHEMA,
        "acceptance_evidence_id": evidence_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "strategy_hash": strategy_hash,
        "experiment_id": experiment_id,
        "campaign_id": campaign_id,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "config_hash": config_hash,
        "selection_criterion": selection_criterion,
        "validation_metrics": dict(validation_metrics or {}),
        "walkforward_metrics": dict(walkforward_metrics or {}),
        "robustness_summary": dict(robustness_summary or {}),
        "dsr": dsr,
        "n_trials": int(n_trials),
        "test_metrics": dict(test_metrics or {}),
        "score": score,
        "acceptance_policy_version": acceptance_policy_version,
        "research_eligibility": elig,
        "sealed_test_ok": sealed_test_ok,
        "robustness_ok": robustness_ok,
        "walkforward_ok": walkforward_ok,
        "dsr_trial_accounting_ok": dsr_trial_accounting_ok,
        "no_leakage": no_leakage,
        "no_unknown_membership_traded": no_unknown_membership_traded,
    }
    digest = state_hash(_payload_for_digest(provisional))
    return StrategyAcceptanceRecord(
        **provisional,
        accepted_at=accepted_at or datetime.now(timezone.utc),
        artifact_digest=digest,
        extras=dict(extras or {}),
    )


def verify_acceptance_record(record: StrategyAcceptanceRecord) -> list[str]:
    """Return blockers if record is inconsistent or non-authoritative."""
    blockers: list[str] = []
    if record.research_eligibility == "development_only":
        blockers.append("development_only_acceptance_forbidden")
    if record.research_eligibility not in {
        "research_eligible",
        "production_candidate",
    }:
        blockers.append(f"eligibility={record.research_eligibility} invalid")
    if not record.sealed_test_ok:
        blockers.append("sealed_test_not_ok")
    if not record.robustness_ok:
        blockers.append("robustness_not_ok")
    if not record.no_leakage:
        blockers.append("leakage_flagged")
    if not record.no_unknown_membership_traded:
        blockers.append("unknown_membership_traded")
    expected_id = make_acceptance_evidence_id(
        campaign_id=record.campaign_id,
        strategy_id=record.strategy_id,
        strategy_version=record.strategy_version,
        config_hash=record.config_hash,
        dataset_id=record.dataset_id,
        dataset_version=record.dataset_version,
    )
    if record.acceptance_evidence_id != expected_id:
        blockers.append("acceptance_evidence_id_mismatch")
    payload = record.to_dict()
    expected_digest = state_hash(_payload_for_digest(payload))
    if record.artifact_digest != expected_digest:
        blockers.append("artifact_digest_mismatch")
    return blockers


def write_acceptance_record(path: Path, record: StrategyAcceptanceRecord) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record.to_dict(), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def load_acceptance_record(path: Path) -> StrategyAcceptanceRecord:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    record = StrategyAcceptanceRecord.model_validate(raw)
    blockers = verify_acceptance_record(record)
    if blockers:
        raise ValueError(f"invalid StrategyAcceptanceRecord: {blockers}")
    return record


def build_acceptance_record_from_campaign_decision(
    *,
    campaign_id: str,
    config_hash: str,
    dataset_id: str,
    dataset_version: str,
    selection_criterion: str,
    research_eligibility: str,
    candidate_id: str,
    strategy_id: str,
    strategy_version: str,
    strategy_hash: str | None,
    experiment_id: str | None,
    metrics: dict[str, Any],
    sealed_test_ok: bool,
    n_trials: int,
    acceptance_policy_version: str = ACCEPTANCE_POLICY_VERSION,
) -> StrategyAcceptanceRecord:
    """Construct record from campaign candidate metrics after acceptance."""
    score_blob = metrics.get("score") or {}
    rob = metrics.get("robustness_summary") or {}
    wf = metrics.get("walkforward_stats") or metrics.get("walkforward_metrics") or {}
    test_m = metrics.get("test") or metrics.get("test_metrics") or {}
    val_m = metrics.get("validation") or metrics.get("validation_metrics") or {}
    dsr = score_blob.get("dsr")
    if dsr is None:
        dsr = metrics.get("dsr")
    score = score_blob.get("score")
    if score is None:
        score = metrics.get("score_value")

    robustness_ok = (
        not bool(rob.get("fragile"))
        and (
            rob.get("pass_rate") is None
            or float(rob.get("pass_rate", 0.0)) >= 0.5
        )
    )
    walkforward_ok = True
    if wf:
        frac = wf.get("fraction_positive_windows")
        if frac is not None and float(frac) < 0.4:
            walkforward_ok = False
    dsr_ok = n_trials >= 0 and (
        dsr is None or (isinstance(dsr, (int, float)) and float(dsr) == float(dsr))
    )
    unknown_traded = bool(metrics.get("unknown_membership_traded", False))
    leakage = bool(metrics.get("feature_leakage", False))

    return build_acceptance_record(
        campaign_id=campaign_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        strategy_hash=strategy_hash,
        experiment_id=experiment_id or candidate_id,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        config_hash=config_hash,
        selection_criterion=selection_criterion,
        research_eligibility=research_eligibility,
        validation_metrics=dict(val_m) if isinstance(val_m, dict) else {},
        walkforward_metrics=dict(wf) if isinstance(wf, dict) else {},
        robustness_summary=dict(rob) if isinstance(rob, dict) else {},
        dsr=float(dsr) if dsr is not None else None,
        n_trials=n_trials,
        test_metrics=dict(test_m) if isinstance(test_m, dict) else {},
        score=float(score) if score is not None else None,
        sealed_test_ok=sealed_test_ok,
        robustness_ok=robustness_ok,
        walkforward_ok=walkforward_ok,
        dsr_trial_accounting_ok=dsr_ok,
        no_leakage=not leakage,
        no_unknown_membership_traded=not unknown_traded,
        acceptance_policy_version=acceptance_policy_version,
        extras={"candidate_id": candidate_id},
    )
