"""Additive value-expression AST (Phase 4).

Expr evaluates to float | None. It does NOT replace Rule (boolean predicates).
No arbitrary code execution — only allowlisted ops via explicit dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from quantfund.strategies.spec.models import Rule

EXPR_OPS = frozenset(
    {
        "constant",
        "feature_ref",
        "add",
        "subtract",
        "multiply",
        "divide",
        "abs",
        "min",
        "max",
        "if",
    }
)


class Expr(BaseModel):
    """Allowlisted value expression node."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    op: Literal[
        "constant",
        "feature_ref",
        "add",
        "subtract",
        "multiply",
        "divide",
        "abs",
        "min",
        "max",
        "if",
    ]
    value: float | None = None
    name: str | None = None
    args: list[Expr] = Field(default_factory=list)
    condition: Any | None = None  # Rule after model_rebuild in models.py
    then: Expr | None = None
    else_: Expr | None = Field(default=None, alias="else")

    @model_validator(mode="after")
    def check_shape(self) -> Expr:
        if self.op == "constant":
            if self.value is None:
                raise ValueError("constant requires value")
        elif self.op == "feature_ref":
            if not self.name or not str(self.name).strip():
                raise ValueError("feature_ref requires name")
        elif self.op == "abs":
            if len(self.args) != 1:
                raise ValueError("abs requires exactly one arg")
        elif self.op in {"add", "subtract", "multiply", "divide", "min", "max"}:
            if len(self.args) < 2:
                raise ValueError(f"{self.op} requires at least two args")
        elif self.op == "if":
            if self.condition is None or self.then is None or self.else_ is None:
                raise ValueError("if requires condition, then, and else")
        return self
