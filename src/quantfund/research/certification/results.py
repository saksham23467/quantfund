"""Shared certification result type."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CertResult:
    dimension: str
    passed: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "passed": self.passed,
            "metrics": self.metrics,
            "blockers": self.blockers,
            "notes": self.notes,
        }
