"""Generate the PIT universe coverage report against the real repository state.

This runner never invents membership. It looks for an authoritative point-in-time
membership ledger; when one is absent (the current repository state) every
session is reported UNKNOWN and research eligibility fails closed. When a ledger
is present it is loaded and scored through
:func:`quantfund.research.universe.coverage.evaluate_research_universe_coverage`.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.models import Instrument
from quantfund.data.universe.import_membership import (
    build_universe_from_membership_file,
)
from quantfund.data.universe.models import UniverseCompleteness
from quantfund.phase17a.datasets import DiscoveredPackage, discover_zerodha_packages
from quantfund.research.universe.coverage import (
    ResearchUniverseCoverage,
    evaluate_research_universe_coverage,
)
from quantfund.research.universe.identity import bind_identity

# Documented location for an authoritative PIT membership ledger. Drop a
# certified membership.(json|csv) here to activate full scoring.
_LEDGER_CANDIDATES = ("membership.json", "membership.csv")


def _package_instrument(pkg: DiscoveredPackage) -> Instrument:
    """Build an Instrument from a package's resolved metadata — never invented."""
    meta_path = pkg.path / "instrument_metadata.json"
    meta: dict[str, Any] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    resolved = meta.get("resolved") if isinstance(meta.get("resolved"), dict) else {}

    def _f(*keys: str) -> Any:
        for src in (meta, resolved):
            for k in keys:
                v = src.get(k)
                if v:
                    return v
        return None

    exchange = _f("exchange") or pkg.manifest.get("exchange") or "NSE"
    isin = _f("isin")  # null in current broker packages → identity stays UNKNOWN
    instrument_id = _f("instrument_id") or f"{exchange}:{pkg.symbol}"
    token = _f("instrument_token", "token")
    return Instrument(
        symbol=pkg.symbol,
        instrument_id=str(instrument_id),
        isin=str(isin) if isin else None,
        exchange=str(exchange),
        metadata={"instrument_token": token} if token else {},
    )


def _ledger_root(root: Path | None) -> Path:
    from quantfund.data.zerodha_hist.package import research_zerodha_root

    base = root if root is not None else research_zerodha_root().parent
    return Path(base) / "universe"


def _find_ledger(universe_id: str, ledger_root: Path) -> Path | None:
    universe_dir = ledger_root / universe_id
    for name in _LEDGER_CANDIDATES:
        cand = universe_dir / name
        if cand.exists():
            return cand
    return None


def _union_range(packages: list[DiscoveredPackage]) -> tuple[date | None, date | None]:
    starts = [p.start for p in packages if p.start]
    ends = [p.end for p in packages if p.end]
    if not starts or not ends:
        return None, None
    start = min(date.fromisoformat(s[:10]) for s in starts)
    end = max(date.fromisoformat(e[:10]) for e in ends)
    return start, end


def build_pit_universe_report(
    *,
    universe_id: str = "nse_research_universe",
    root: Path | None = None,
    ledger_root: Path | None = None,
    symbols: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Assemble the coverage payload honestly reflecting available evidence."""
    packages = discover_zerodha_packages(root=root, symbols=symbols)
    instruments = {p.symbol: _package_instrument(p) for p in packages}
    by_id = {inst.instrument_id: inst for inst in instruments.values()}
    start, end = _union_range(packages)

    resolved_ledger_root = _ledger_root(ledger_root)
    ledger_path = _find_ledger(universe_id, resolved_ledger_root)

    generated_at = datetime.now(timezone.utc).isoformat()
    base: dict[str, Any] = {
        "generated_at": generated_at,
        "universe_id": universe_id,
        "package_count": len(packages),
        "symbols": sorted(instruments),
        "membership_ledger": str(ledger_path) if ledger_path else None,
        "membership_ledger_search_path": str(resolved_ledger_root / universe_id),
        "price_ca_separation": (
            "This layer resolves membership + identity only; it never reads or "
            "adjusts execution prices, so corporate actions stay separate from "
            "RAW prices."
        ),
        "trading_enabled": False,
    }

    # Identity coverage is measurable regardless of membership evidence.
    bindings = [bind_identity(inst) for inst in instruments.values()]
    authoritative = sum(1 for b in bindings if b.is_authoritative)
    identity_cov = (authoritative / len(bindings)) if bindings else 0.0

    if ledger_path is None:
        # Honest fail-closed state: no PIT membership ledger exists.
        session_count = 0
        if start is not None and end is not None:
            try:
                cal = NSECalendarProvider()
                cov_start = max(start, cal.metadata().effective_start)
                cov_end = min(end, cal.metadata().effective_end)
                session_count = len(cal.sessions_in_range(cov_start, cov_end))
            except Exception:  # pragma: no cover - calendar optional for report
                session_count = 0
        unknown = session_count * len(instruments)
        base.update(
            {
                "completeness": "none",
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
                "session_count": session_count,
                "instrument_count": len(instruments),
                "membership_coverage_ratio": 0.0,
                "unknown_membership_count": unknown,
                "true_membership_sessions": 0,
                "false_membership_sessions": 0,
                "instrument_identity_coverage": identity_cov,
                "authoritative_identity_count": authoritative,
                "delisted_coverage": "none",
                "delisted_coverage_ratio": 0.0,
                "delisted_known_instruments": 0,
                "research_eligibility": False,
                "blockers": [
                    "missing_pit_membership_ledger",
                    "unknown_membership_sessions_gt_0",
                    "instrument_identity_coverage_below_1.0",
                    "delisted_coverage_insufficient",
                ],
                "identity_bindings": [b.to_dict() for b in bindings],
                "notes": [
                    "No authoritative PIT membership ledger found; membership is "
                    "UNKNOWN for every historical session (not invented as TRUE).",
                    "Broker packages carry a null ISIN, so stable exchange:ISIN "
                    "identity is not established.",
                    "research_eligibility=false — universe layer is NOT research-grade.",
                ],
            }
        )
        return base

    # Ledger present → score it through the shared evaluator.
    if start is None or end is None:
        start = date.today()
        end = date.today()
    universe = build_universe_from_membership_file(
        ledger_path,
        universe_id=universe_id,
        universe_version="v1",
        effective_start=start,
        effective_end=end,
        source="authoritative_membership_ledger",
        completeness=UniverseCompleteness.PARTIAL_PIT,
    )
    cal = NSECalendarProvider()
    cov_start = max(start, cal.metadata().effective_start)
    cov_end = min(end, cal.metadata().effective_end)
    coverage: ResearchUniverseCoverage = evaluate_research_universe_coverage(
        universe,
        calendar=cal,
        start=cov_start,
        end=cov_end,
        instruments=by_id,
        terminal_events=None,
    )
    base.update(coverage.to_dict())
    base["identity_bindings"] = [b.to_dict() for b in bindings]
    return base


def _md_report(payload: dict[str, Any]) -> str:
    eligible = payload.get("research_eligibility", False)
    verdict = "RESEARCH-GRADE" if eligible else "NOT RESEARCH-GRADE (fail closed)"
    lines = [
        "# PIT Historical Universe Layer",
        "",
        f"_Generated: {payload.get('generated_at')}_",
        "",
        "## Verdict",
        "",
        f"**research_eligibility = {str(eligible).lower()}** — {verdict}.",
        "",
        "Paper and live trading remain disabled. This layer touches membership + "
        "identity only and never reads or adjusts execution prices, so corporate "
        "actions stay separate from RAW prices.",
        "",
        "## Coverage metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| membership_coverage_ratio | {payload.get('membership_coverage_ratio')} |",
        f"| instrument_identity_coverage | {payload.get('instrument_identity_coverage')} |",
        f"| delisted_coverage | {payload.get('delisted_coverage')} |",
        f"| unknown_membership_count | {payload.get('unknown_membership_count')} |",
        f"| research_eligibility | {str(eligible).lower()} |",
        f"| session_count | {payload.get('session_count')} |",
        f"| instrument_count | {payload.get('instrument_count')} |",
        f"| completeness | {payload.get('completeness')} |",
        "",
        "## Blockers",
        "",
    ]
    blockers = payload.get("blockers") or []
    if blockers:
        lines.extend(f"- `{b}`" for b in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Notes", ""])
    for note in payload.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def write_pit_universe_report(
    payload: dict[str, Any],
    *,
    json_path: Path,
    md_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_md_report(payload), encoding="utf-8")
