"""Development-data human-readable report — never claims RESEARCH_ELIGIBLE."""

from __future__ import annotations

from typing import Any

from quantfund.data.development.manifest import DevelopmentManifest


def format_development_report(
    manifest: DevelopmentManifest,
    *,
    quality: dict[str, Any] | None = None,
    research_eligibility: str = "development_only",
) -> str:
    q = quality or {}
    lines = [
        "=== DEVELOPMENT DATA REPORT ===",
        "",
        "Dataset:",
        manifest.dataset_id,
        "",
        "Source:",
        manifest.source,
        "",
        "Data class:",
        "DEVELOPMENT_DATA",
        "",
        "Research grade:",
        "FALSE",
        "",
        "Research eligible:",
        "FALSE",
        "",
        "Paper eligible:",
        "FALSE",
        "",
        "Live eligible:",
        "FALSE",
        "",
        "PIT:",
        manifest.pit_membership.upper(),
        "",
        "Delisted coverage:",
        manifest.delisted_coverage.upper(),
        "",
        "Corporate actions:",
        manifest.corporate_action_coverage,
        "",
        "Quality:",
        q.get("quality", "PASS" if manifest.quality_pass else "FAIL"),
        "",
        "Synthetic:",
        str(manifest.synthetic).upper(),
        "",
        f"Research eligibility level: {research_eligibility}",
        f"Content hash: {manifest.content_hash}",
        "",
        "Claims:",
        "NONE",
        "",
        "WARNING:",
        "DEVELOPMENT_DATA IS FOR ENGINEERING AND RESEARCH DEVELOPMENT ONLY.",
        "IT DOES NOT CONSTITUTE RESEARCH-GRADE MARKET DATA.",
        "IT CANNOT AUTHORIZE PAPER OR LIVE TRADING.",
    ]
    # Hard guarantee: never emit RESEARCH_ELIGIBLE as a positive claim
    text = "\n".join(lines)
    assert "RESEARCH_ELIGIBLE: TRUE" not in text
    return text
