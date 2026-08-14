"""Structured StrategySpecValidator (Phase 4) alongside raising validator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.strategies.spec.dsl import ComplexityLimits, DEFAULT_COMPLEXITY_LIMITS
from quantfund.strategies.spec.models import StrategySpec
from quantfund.strategies.spec.validate import ValidationError, validate_strategy_spec


@dataclass(frozen=True)
class SpecValidationIssue:
    path: str
    code: str
    message: str


@dataclass
class StrategySpecValidationResult:
    valid: bool
    errors: list[SpecValidationIssue] = field(default_factory=list)
    warnings: list[SpecValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if self.valid:
            return {"status": "VALID", "errors": [], "warnings": [w.__dict__ for w in self.warnings]}
        return {
            "status": "INVALID",
            "errors": [e.__dict__ for e in self.errors],
            "warnings": [w.__dict__ for w in self.warnings],
        }


def _classify_error(message: str) -> tuple[str, str]:
    """Map legacy ValidationError messages to (path, code)."""
    msg = message.lower()
    if "feature not allowlisted" in msg:
        return "features", "unknown_feature"
    if "op not allowlisted" in msg:
        return "rules", "unknown_operator"
    if "nesting too deep" in msg or "expression nesting" in msg:
        return "rules", "excessive_depth"
    if "node count" in msg:
        return "rules", "excessive_nodes"
    if "too many rules" in msg:
        return "rules", "excessive_rules"
    if "too many features" in msg:
        return "features", "excessive_features"
    if "too many parameters" in msg:
        return "parameters", "excessive_parameters"
    if "forbidden token" in msg:
        return "spec", "malicious_payload"
    if "non-finite" in msg or "finite number" in msg:
        return "rules", "non_finite_constant"
    if "invalid window" in msg:
        return "features.params", "invalid_parameter"
    if "position_sizing" in msg:
        return "position_sizing", "invalid_sizing"
    if "risk_constraints" in msg:
        return "risk_constraints", "invalid_risk"
    if "operand" in msg:
        return "rules", "invalid_operand"
    if "arithmetic/value op" in msg:
        return "rules", "value_op_as_rule"
    if "name required" in msg or "name too long" in msg:
        return "name", "invalid_name"
    if "entry_rules" in msg:
        return "entry_rules", "missing_entry_rules"
    if "hypothesis" in msg:
        return "hypothesis", "hypothesis_too_long"
    if "universe" in msg:
        return "universe_id", "invalid_universe"
    return "spec", "validation_error"


class StrategySpecValidator:
    """Structured validator — never executes strategy payloads."""

    def __init__(self, limits: ComplexityLimits | None = None) -> None:
        self.limits = limits or DEFAULT_COMPLEXITY_LIMITS

    def validate(self, spec: StrategySpec | dict[str, Any]) -> StrategySpecValidationResult:
        errors: list[SpecValidationIssue] = []
        warnings: list[SpecValidationIssue] = []
        try:
            if isinstance(spec, dict):
                # Reject obvious code-shaped dict keys before model parse where possible
                spec = StrategySpec.model_validate(spec)
        except Exception as exc:  # noqa: BLE001
            return StrategySpecValidationResult(
                valid=False,
                errors=[
                    SpecValidationIssue(
                        path="spec",
                        code="schema_error",
                        message=str(exc),
                    )
                ],
            )

        try:
            validate_strategy_spec(spec, limits=self.limits)
        except ValidationError as exc:
            path, code = _classify_error(str(exc))
            errors.append(SpecValidationIssue(path=path, code=code, message=str(exc)))
            return StrategySpecValidationResult(valid=False, errors=errors, warnings=warnings)

        if not spec.universe_id.strip():
            errors.append(
                SpecValidationIssue(
                    path="universe_id",
                    code="invalid_universe",
                    message="universe_id required",
                )
            )
        if spec.metadata.get("accepted") or spec.metadata.get("accepted_for_validation_pipeline"):
            errors.append(
                SpecValidationIssue(
                    path="metadata",
                    code="self_acceptance_forbidden",
                    message="StrategySpec must not claim acceptance",
                )
            )

        if errors:
            return StrategySpecValidationResult(valid=False, errors=errors, warnings=warnings)
        return StrategySpecValidationResult(valid=True, errors=[], warnings=warnings)
