"""Dataset Certification service — reads the REAL certification report (the moat)."""

from __future__ import annotations

import json

from quantfund_terminal.backend.app.config import REPORTS_DIR

_WHY_IT_MATTERS = (
    "Most 'quant' platforms backtest on survivorship-biased, corporate-action-"
    "naive, non-authoritative data — producing beautiful, unreproducible lies. "
    "QuantFund certifies data provenance BEFORE any strategy can be accepted. A "
    "DEVELOPMENT_ONLY verdict is a feature: the system fails closed instead of "
    "manufacturing a false edge."
)


def _read(name: str) -> dict:
    path = REPORTS_DIR / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_certification() -> dict:
    cert = _read("research_data_certification.json")
    pit = _read("pit_universe_coverage.json")

    if not cert:
        return {
            "available": False,
            "verdict": "DEVELOPMENT_ONLY",
            "why_it_matters": _WHY_IT_MATTERS,
            "note": "No certification report found; failing closed to DEVELOPMENT_ONLY.",
        }

    return {
        "available": True,
        "verdict": cert.get("verdict", "DEVELOPMENT_ONLY"),
        "research_eligible": cert.get("research_eligible", False),
        "eligibility_level": cert.get("eligibility_level"),
        "source_grade": cert.get("source_grade"),
        "data_class": cert.get("data_class"),
        "content_hash": cert.get("content_hash"),
        "reproducible": cert.get("reproducible"),
        "immutable": cert.get("immutable"),
        "leakage_safe": cert.get("leakage_safe"),
        "dimensions": {
            "source_grade": cert.get("source_grade"),
            "capability_source_bar_ok": cert.get("capability_source_bar_ok"),
            "calendar_quality": cert.get("calendar_quality"),
            "membership_coverage_ratio": cert.get("membership_coverage_ratio"),
            "instrument_identity_coverage": cert.get("instrument_identity_coverage"),
            "delisted_coverage": cert.get("delisted_coverage"),
            "corporate_action_coverage": cert.get("corporate_action_coverage"),
            "coverage": cert.get("coverage"),
        },
        "blockers": cert.get("blockers", []),
        "capability_gaps": cert.get("capability_gaps", []),
        "pit_universe": {
            "completeness": pit.get("completeness"),
            "membership_coverage_ratio": pit.get("membership_coverage_ratio"),
            "blockers": pit.get("blockers", []),
        },
        "safety_state": cert.get("safety_state", {}),
        "why_it_matters": _WHY_IT_MATTERS,
        "generated_at": cert.get("generated_at"),
    }
