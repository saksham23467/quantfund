"""Feature / membership / execution drift monitoring (Phase 10).

Drift produces warnings or hard failures per versioned policy.
Does NOT automatically modify the strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


DRIFT_POLICY_VERSION = "drift_policy_v1"


class DriftSeverity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    HARD_FAIL = "HARD_FAIL"


class DriftPolicyV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str = DRIFT_POLICY_VERSION
    max_feature_mean_z: float = 3.0
    max_missing_feature_rate: float = 0.05
    max_membership_change_rate: float = 0.20
    max_data_gap_sessions: int = 0
    max_turnover_ratio: float = 2.0
    max_signal_frequency_ratio: float = 2.0
    max_exposure_delta: float = 0.30
    hard_fail_on_missing_features: bool = True
    hard_fail_on_data_gaps: bool = True
    hard_fail_on_ca_unhandled: bool = False


@dataclass
class DriftFinding:
    code: str
    severity: DriftSeverity
    message: str
    value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "value": self.value,
        }


@dataclass
class DriftReport:
    policy_id: str
    severity: DriftSeverity
    findings: list[DriftFinding] = field(default_factory=list)
    strategy_modified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "severity": self.severity.value,
            "findings": [f.to_dict() for f in self.findings],
            "strategy_modified": self.strategy_modified,
        }


def evaluate_drift(
    *,
    baseline: dict[str, Any],
    observed: dict[str, Any],
    policy: DriftPolicyV1 | None = None,
    corporate_action_events: list[dict[str, Any]] | None = None,
    membership_changes: list[dict[str, Any]] | None = None,
    data_gaps: int = 0,
) -> DriftReport:
    pol = policy or DriftPolicyV1()
    findings: list[DriftFinding] = []

    # Feature distribution drift (mean z-scores dict)
    feat_z = observed.get("feature_mean_z") or {}
    if isinstance(feat_z, dict):
        for name, z in feat_z.items():
            try:
                zv = abs(float(z))
            except (TypeError, ValueError):
                continue
            if zv > pol.max_feature_mean_z:
                findings.append(
                    DriftFinding(
                        code="feature_distribution_drift",
                        severity=DriftSeverity.WARNING,
                        message=f"{name} mean z={zv}",
                        value=zv,
                    )
                )

    miss_rate = float(observed.get("missing_feature_rate") or 0.0)
    if miss_rate > pol.max_missing_feature_rate:
        sev = (
            DriftSeverity.HARD_FAIL
            if pol.hard_fail_on_missing_features
            else DriftSeverity.WARNING
        )
        findings.append(
            DriftFinding(
                code="missing_features",
                severity=sev,
                message=f"missing_feature_rate={miss_rate}",
                value=miss_rate,
            )
        )

    mem = membership_changes or observed.get("membership_changes") or []
    base_n = max(int(baseline.get("universe_size") or 1), 1)
    change_rate = len(mem) / base_n
    if change_rate > pol.max_membership_change_rate:
        findings.append(
            DriftFinding(
                code="membership_changes",
                severity=DriftSeverity.WARNING,
                message=f"membership_change_rate={change_rate}",
                value=change_rate,
            )
        )

    ca = corporate_action_events or observed.get("corporate_action_events") or []
    unhandled = [e for e in ca if e.get("handled") is False]
    if unhandled:
        sev = (
            DriftSeverity.HARD_FAIL
            if pol.hard_fail_on_ca_unhandled
            else DriftSeverity.WARNING
        )
        findings.append(
            DriftFinding(
                code="corporate_action_events",
                severity=sev,
                message=f"unhandled_ca={len(unhandled)}",
                value=float(len(unhandled)),
            )
        )

    if data_gaps > pol.max_data_gap_sessions:
        sev = (
            DriftSeverity.HARD_FAIL
            if pol.hard_fail_on_data_gaps
            else DriftSeverity.WARNING
        )
        findings.append(
            DriftFinding(
                code="data_gaps",
                severity=sev,
                message=f"data_gaps={data_gaps}",
                value=float(data_gaps),
            )
        )

    base_to = float(baseline.get("turnover") or 0.0)
    obs_to = float(observed.get("turnover") or 0.0)
    if base_to > 0 and obs_to / base_to > pol.max_turnover_ratio:
        findings.append(
            DriftFinding(
                code="unexpected_turnover",
                severity=DriftSeverity.WARNING,
                message=f"turnover_ratio={obs_to / base_to}",
                value=obs_to / base_to,
            )
        )

    base_sf = float(baseline.get("signal_frequency") or 0.0)
    obs_sf = float(observed.get("signal_frequency") or 0.0)
    if base_sf > 0 and obs_sf / base_sf > pol.max_signal_frequency_ratio:
        findings.append(
            DriftFinding(
                code="signal_frequency_changes",
                severity=DriftSeverity.WARNING,
                message=f"signal_frequency_ratio={obs_sf / base_sf}",
                value=obs_sf / base_sf,
            )
        )

    base_exp = float(baseline.get("exposure") or 0.0)
    obs_exp = float(observed.get("exposure") or 0.0)
    if abs(obs_exp - base_exp) > pol.max_exposure_delta:
        findings.append(
            DriftFinding(
                code="exposure_changes",
                severity=DriftSeverity.WARNING,
                message=f"exposure_delta={obs_exp - base_exp}",
                value=obs_exp - base_exp,
            )
        )

    severity = DriftSeverity.OK
    for f in findings:
        if f.severity == DriftSeverity.HARD_FAIL:
            severity = DriftSeverity.HARD_FAIL
            break
        if f.severity == DriftSeverity.WARNING:
            severity = DriftSeverity.WARNING

    return DriftReport(
        policy_id=pol.policy_id,
        severity=severity,
        findings=findings,
        strategy_modified=False,
    )
