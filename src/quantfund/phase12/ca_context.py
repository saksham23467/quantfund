"""Bridge into existing corporate-action infrastructure (no second CA system)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from quantfund.data.corporate_actions.models import CorporateAction


@dataclass
class PaperCAContext:
    """As-of CA view for paper session accounting/features — RAW OHLC untouched."""

    actions: list[CorporateAction] = field(default_factory=list)
    incomplete_instruments: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    future_visibility_violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts and not self.future_visibility_violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_count": len(self.actions),
            "incomplete_instruments": list(self.incomplete_instruments),
            "conflicts": list(self.conflicts),
            "future_visibility_violations": list(self.future_visibility_violations),
            "ok": self.ok,
        }


def build_paper_ca_context(
    actions: list[CorporateAction],
    *,
    as_of: date,
    allow_incomplete: bool = True,
) -> PaperCAContext:
    """Filter CA records as-of without inventing merger/demerger prices."""
    visible: list[CorporateAction] = []
    incomplete: list[str] = []
    conflicts: list[str] = []
    future_violations: list[str] = []

    seen_keys: set[tuple[str, str, str]] = set()
    for ca in actions:
        ex = getattr(ca, "ex_date", None) or getattr(ca, "effective_date", None)
        if ex is None:
            incomplete.append(getattr(ca, "symbol", "UNKNOWN"))
            if not allow_incomplete:
                conflicts.append("incomplete_ca_missing_ex_date")
            continue
        if ex > as_of:
            # Future CA must not be visible for trading decisions as-of
            future_violations.append(
                f"{getattr(ca, 'symbol', '?')}:{ex.isoformat()}"
            )
            continue
        key = (
            str(getattr(ca, "symbol", "")),
            str(getattr(ca, "action_type", "")),
            ex.isoformat(),
        )
        if key in seen_keys:
            conflicts.append(f"duplicate_ca:{key}")
            continue
        seen_keys.add(key)
        visible.append(ca)

    return PaperCAContext(
        actions=visible,
        incomplete_instruments=sorted(set(incomplete)),
        conflicts=conflicts,
        future_visibility_violations=future_violations,
    )
