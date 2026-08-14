"""Terminal / delisting event infrastructure.

A stock disappearing from today's instrument list must NOT mean it never existed.
Mergers/demergers are recorded but never auto-mapped into price reconstructions.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quantfund.data.models import Instrument
from quantfund.data.policy import DelistedCoverage


class TerminalEventType(str, Enum):
    DELISTING = "delisting"
    SYMBOL_CHANGE = "symbol_change"
    MERGER = "merger"
    DEMERGER = "demerger"
    ACQUIRED = "acquired"
    SUSPENDED = "suspended"
    RENAMED = "renamed"
    OTHER = "other"


# Design synonym — prefer TerminalEvent; alias for docs/call sites.
InstrumentTerminalEventType = TerminalEventType


class TerminalEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    instrument_id: str
    symbol: str
    event_type: TerminalEventType
    event_date: date
    last_trade_date: date | None = None
    predecessor_instrument_id: str | None = None
    successor_instrument_id: str | None = None
    source: str
    source_ref: str | None = None
    verification_status: str = "unverified"
    confidence: str = "unknown"  # unknown | low | medium | high | verified
    provenance: dict[str, Any] = Field(default_factory=dict)
    requires_manual_treatment: bool = False
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        if self.event_type in {
            TerminalEventType.MERGER,
            TerminalEventType.DEMERGER,
            TerminalEventType.ACQUIRED,
        }:
            object.__setattr__(self, "requires_manual_treatment", True)
        if self.last_trade_date is None:
            object.__setattr__(self, "last_trade_date", self.event_date)


# Alias per Phase 5 architecture
InstrumentTerminalEvent = TerminalEvent


class TerminalEventStore:
    """Versioned store for delisting / terminal events."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, catalog_id: str, catalog_version: str) -> Path:
        return (
            self.root
            / catalog_id
            / f"catalog_version={catalog_version}"
            / "terminal_events.json"
        )

    def save(
        self,
        *,
        catalog_id: str,
        catalog_version: str,
        events: list[TerminalEvent],
        source: str,
    ) -> Path:
        path = self.path_for(catalog_id, catalog_version)
        if path.exists():
            raise FileExistsError(f"Terminal event catalog immutable: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([e.model_dump(mode="json") for e in events], indent=2),
            encoding="utf-8",
        )
        meta = {
            "catalog_id": catalog_id,
            "catalog_version": catalog_version,
            "source": source,
            "event_count": len(events),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": (
                "Mergers/demergers require manual treatment; "
                "no automatic price reconstruction."
            ),
        }
        (path.parent / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return path

    def load(self, catalog_id: str, catalog_version: str) -> list[TerminalEvent]:
        path = self.path_for(catalog_id, catalog_version)
        data = json.loads(path.read_text(encoding="utf-8"))
        return [TerminalEvent.model_validate(row) for row in data]


def check_delisting_terminal_consistency(
    instruments: list[Instrument],
    events: list[TerminalEvent],
) -> list:
    """Reconcile Instrument.delisting_date with TerminalEvent ledger."""
    # Lazy import avoids circular import via quality.checks → delisted
    from quantfund.data.quality.report import QualityIssue, Severity

    issues: list = []
    delist_events = {
        e.instrument_id: e
        for e in events
        if e.event_type == TerminalEventType.DELISTING
    }
    for inst in instruments:
        iid = inst.instrument_id or inst.symbol
        ev = delist_events.get(iid)
        if inst.delisting_date and ev is None:
            issues.append(
                QualityIssue(
                    severity=Severity.WARNING,
                    code="delisting_missing_terminal_event",
                    message=(
                        f"{inst.symbol} has delisting_date={inst.delisting_date} "
                        "but no TerminalEvent.DELISTING"
                    ),
                    symbol=inst.symbol,
                )
            )
        elif inst.delisting_date and ev is not None and ev.event_date != inst.delisting_date:
            issues.append(
                QualityIssue(
                    severity=Severity.ERROR,
                    code="delisting_date_inconsistency",
                    message=(
                        f"{inst.symbol} delisting_date={inst.delisting_date} "
                        f"!= terminal event_date={ev.event_date}"
                    ),
                    symbol=inst.symbol,
                )
            )
        elif ev is not None and inst.delisting_date is None:
            issues.append(
                QualityIssue(
                    severity=Severity.WARNING,
                    code="terminal_event_missing_delisting_date",
                    message=(
                        f"{inst.symbol} has TerminalEvent.DELISTING but "
                        "Instrument.delisting_date is unset"
                    ),
                    symbol=inst.symbol,
                )
            )

    # Impossible / contradictory terminal events
    for ev in events:
        if ev.last_trade_date and ev.last_trade_date > ev.event_date:
            issues.append(
                QualityIssue(
                    severity=Severity.ERROR,
                    code="impossible_terminal_event",
                    message=(
                        f"Terminal event {ev.event_id}: last_trade_date "
                        f"{ev.last_trade_date} after event_date {ev.event_date}"
                    ),
                    symbol=ev.symbol,
                    details={"event_id": ev.event_id},
                )
            )
        if (
            ev.event_type == TerminalEventType.MERGER
            and not ev.successor_instrument_id
            and ev.verification_status == "verified"
        ):
            issues.append(
                QualityIssue(
                    severity=Severity.WARNING,
                    code="merger_missing_successor",
                    message=(
                        f"Verified merger {ev.event_id} lacks successor_instrument_id"
                    ),
                    symbol=ev.symbol,
                )
            )
    return issues


def compute_delisted_coverage(
    *,
    instruments: list[Instrument],
    events: list[TerminalEvent] | None,
    expected_terminal_instrument_ids: set[str] | None = None,
) -> str:
    """Derive delisted_coverage from instrument master + terminal ledger.

    - none: no terminal ledger and no delisting_date on instruments
    - partial: some evidence, incomplete vs expected set
    - complete: every expected terminal instrument has a verified delisting event
      (or all delisted instruments have matching events when expected set omitted)
    - unknown: ledger present but unverifiable / empty expected with mixed signals
    """
    events = list(events or [])
    delisted_inst = [i for i in instruments if i.delisting_date is not None]
    if not events and not delisted_inst:
        return DelistedCoverage.NONE.value

    by_id = {e.instrument_id: e for e in events if e.event_type == TerminalEventType.DELISTING}
    if expected_terminal_instrument_ids is not None:
        expected = set(expected_terminal_instrument_ids)
        if not expected:
            return DelistedCoverage.COMPLETE.value if events or not delisted_inst else DelistedCoverage.NONE.value
        covered = {iid for iid in expected if iid in by_id}
        if covered == expected and all(
            by_id[i].verification_status == "verified" for i in expected
        ):
            return DelistedCoverage.COMPLETE.value
        if covered:
            return DelistedCoverage.PARTIAL.value
        return DelistedCoverage.UNKNOWN.value

    if not delisted_inst:
        # Events without delisted instruments → partial evidence
        return DelistedCoverage.PARTIAL.value

    matched = 0
    for inst in delisted_inst:
        iid = inst.instrument_id or inst.symbol
        ev = by_id.get(iid)
        if ev is None:
            continue
        if inst.delisting_date and ev.event_date != inst.delisting_date:
            continue
        matched += 1

    if matched == 0:
        return DelistedCoverage.UNKNOWN.value if events else DelistedCoverage.NONE.value
    if matched == len(delisted_inst) and all(
        by_id.get(i.instrument_id or i.symbol)
        and by_id[i.instrument_id or i.symbol].verification_status == "verified"
        for i in delisted_inst
    ):
        return DelistedCoverage.COMPLETE.value
    return DelistedCoverage.PARTIAL.value
