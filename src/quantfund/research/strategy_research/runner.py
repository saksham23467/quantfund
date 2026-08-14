"""Top-level Phase 19 runner: gather authoritative eligibility, then gate search.

Reads the authoritative research-eligibility verdicts (Phase 18 dataset gate and
the PIT universe coverage report), runs the controlled search behind the
prerequisite, and writes the mandated artifacts. In the current repository the
prerequisite is FALSE, so no candidate is enumerated and the funnel is all zero.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.research.strategy_research.framework import (
    StrategyResearchResult,
    run_strategy_research,
)
from quantfund.research.strategy_research.report import (
    build_report_payload,
    write_reports,
)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def gather_eligibility(
    *, reports_dir: Path, run_phase18: bool = True
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (phase18_payload, pit_payload) from authoritative sources."""
    pit_payload = _load_json(reports_dir / "pit_universe_coverage.json")

    phase18_payload = _load_json(reports_dir / "phase18_dataset_eligibility.json")
    if phase18_payload is None and run_phase18:
        # Authoritative, read-only re-evaluation (never enables trading).
        from quantfund.phase18.dataset_eligibility import (
            run_phase18_dataset_eligibility,
        )

        phase18_payload = run_phase18_dataset_eligibility(write_reports=False)
    return phase18_payload, pit_payload


def run_phase19_strategy_research(
    *,
    reports_dir: Path | None = None,
    docs_dir: Path | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Execute the gated Phase 19 research and write the mandated reports."""
    root = Path.cwd()
    reports_dir = reports_dir or (root / "reports")
    docs_dir = docs_dir or (root / "docs")

    phase18_payload, pit_payload = gather_eligibility(reports_dir=reports_dir)

    result: StrategyResearchResult = run_strategy_research(
        phase18_payload=phase18_payload,
        pit_payload=pit_payload,
        context=None,  # only needed once the prerequisite is satisfied
        evaluator=None,
    )
    payload = build_report_payload(result)

    if write:
        write_reports(
            payload,
            json_path=reports_dir / "phase19_strategy_search.json",
            md_path=docs_dir / "PHASE19_STRATEGY_RESEARCH.md",
        )
    return payload
