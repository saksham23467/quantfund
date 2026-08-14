"""Ingest free/public data into DEVELOPMENT_DATA storage + certify as DEVELOPMENT_ONLY."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from quantfund.config import PATHS
from quantfund.data.development.config import (
    DATA_CLASS_DEVELOPMENT,
    DevelopmentIngestConfig,
    PROVIDER_ID,
    SOURCE_GRADE,
)
from quantfund.data.development.manifest import build_manifest
from quantfund.data.development.normalize import bars_summary, instruments_from_bars
from quantfund.data.development.provider import DevelopmentDataProvider
from quantfund.data.development.quality import run_development_quality_checks
from quantfund.data.development.report import format_development_report
from quantfund.data.development.storage import (
    development_dataset_root,
    write_development_dataset,
)
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel


@dataclass
class DevelopmentIngestResult:
    success: bool
    root: Path | None
    manifest_path: Path | None
    data_class: str
    research_eligibility: str
    research_eligible: bool
    paper_eligible: bool
    live_eligible: bool
    synthetic: bool
    research_grade: bool
    real_orders: int
    quality: dict[str, Any]
    report_text: str
    blockers: list[str] = field(default_factory=list)
    facts: DatasetCertificationFacts | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "root": str(self.root) if self.root else None,
            "data_class": self.data_class,
            "research_eligibility": self.research_eligibility,
            "research_eligible": self.research_eligible,
            "paper_eligible": self.paper_eligible,
            "live_eligible": self.live_eligible,
            "synthetic": self.synthetic,
            "research_grade": self.research_grade,
            "real_orders": self.real_orders,
            "quality": self.quality,
            "blockers": list(self.blockers),
        }


def _facts_from_development(
    *,
    dataset_id: str,
    dataset_version: str,
    content_hash: str,
    source: str,
    synthetic: bool,
    summary: dict[str, Any],
    quality_error_count: int,
    quality_codes: list[str],
) -> DatasetCertificationFacts:
    return DatasetCertificationFacts(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source=source,
        source_grade=SOURCE_GRADE,
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,  # calendar may be verified; data_class still blocks
        universe_id="development_current_snapshot",
        universe_version="current_snapshot",
        universe_completeness="current_snapshot_only",
        corporate_action_coverage="none",
        adjustment_policy_id="none",
        date_coverage_start=summary.get("date_coverage_start") or "1970-01-01",
        date_coverage_end=summary.get("date_coverage_end") or "1970-01-01",
        instrument_count=int(summary.get("instrument_count") or 0),
        delisted_coverage="none",
        error_count=quality_error_count,
        content_hash=content_hash,
        quality_error_codes=quality_codes,
        unknown_membership_session_count=1,  # PIT unavailable → unknown sessions
        membership_coverage_ratio=0.0,
        capability_source_bar_ok=False,
        provenance_complete=False,
        license_status="unknown",
        data_class=DATA_CLASS_DEVELOPMENT,
        extras={
            "data_class": DATA_CLASS_DEVELOPMENT,
            "synthetic": synthetic,
            "research_grade": False,
            "exchange_authority": False,
            "pit_membership": "unavailable",
        },
    )


def ingest_development_data(
    config: DevelopmentIngestConfig | None = None,
) -> DevelopmentIngestResult:
    """Fetch/import → normalize → quality → store → force DEVELOPMENT_ONLY."""
    cfg = config or DevelopmentIngestConfig()
    version = cfg.dataset_version or datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    ) + "_" + uuid4().hex[:8]

    # Resolve bars
    if cfg.file_path is not None:
        provider = DevelopmentDataProvider.from_file(Path(cfg.file_path))
    elif cfg.allow_network_fetch:
        provider = DevelopmentDataProvider.from_yfinance_fetch(cfg.symbols)
    else:
        # Offline default: bundled fixture (real-format sample, not research-grade)
        fixture = (
            Path(__file__).resolve().parents[4]
            / "tests"
            / "fixtures"
            / "development"
            / "sample_ohlcv"
        )
        if not fixture.exists():
            # Fallback: tiny in-memory sample for environments without fixture yet
            from quantfund.data.models import MarketBar

            bars = [
                MarketBar(
                    timestamp=datetime(2024, 1, 2),
                    symbol="RELIANCE",
                    open=100,
                    high=101,
                    low=99,
                    close=100.5,
                    volume=1000,
                ),
                MarketBar(
                    timestamp=datetime(2024, 1, 3),
                    symbol="RELIANCE",
                    open=100.5,
                    high=102,
                    low=100,
                    close=101,
                    volume=1100,
                ),
            ]
            provider = DevelopmentDataProvider(
                bars=bars, source_label="embedded_sample", synthetic=False
            )
        else:
            provider = DevelopmentDataProvider.from_file(fixture)

    bars = list(getattr(provider, "_bars", []))
    if not bars:
        for inst in provider.get_instruments():
            bars.extend(provider.get_history(inst.symbol))

    instruments = instruments_from_bars(bars)
    if not bars:
        raise ValueError("development ingest produced zero bars")
    summary = bars_summary(bars)
    qrep = run_development_quality_checks(bars)

    root = development_dataset_root(
        dataset_id=cfg.dataset_id,
        dataset_version=version,
        base=cfg.output_root,
    )
    # provisional manifest for write (hash filled by storage)
    manifest = build_manifest(
        dataset_id=cfg.dataset_id,
        dataset_version=version,
        content_hash="sha256:pending",
        synthetic=provider.synthetic,
        source=provider.attestation()["source_label"],
        universe_mode=cfg.universe_mode,
        corporate_action_coverage="none",
        delisted_coverage="none",
        instrument_count=summary["instrument_count"],
        bar_count=summary["bar_count"],
        date_coverage_start=summary["date_coverage_start"],
        date_coverage_end=summary["date_coverage_end"],
        quality_pass=qrep.ok,
        quality_error_count=qrep.error_count,
        quality_warning_count=qrep.warning_count,
        extras={"provider_id": PROVIDER_ID},
    )
    written = write_development_dataset(
        root=root, bars=bars, instruments=instruments, manifest=manifest
    )
    from quantfund.data.development.storage import load_development_manifest

    final_manifest = load_development_manifest(written)

    facts = _facts_from_development(
        dataset_id=cfg.dataset_id,
        dataset_version=version,
        content_hash=final_manifest.content_hash,
        source=final_manifest.source,
        synthetic=final_manifest.synthetic,
        summary=summary,
        quality_error_count=qrep.error_count,
        quality_codes=list({i.split(":")[0] for i in qrep.issues}),
    )
    decision = ResearchEligibilityChecker().evaluate(facts)
    assert decision.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert decision.is_research_eligible is False

    # Paper / live gates (data rung)
    from quantfund.paper.eligibility import PaperEligibilityGate
    from quantfund.paper.models import SessionMode
    from quantfund.execution.live_eligibility import LiveTradingEligibilityGate

    paper = PaperEligibilityGate().evaluate(
        certified_eligibility=decision.level.value,
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id="dev_must_not_pass",
        facts=facts,
        sealed_test_ok=True,
        robustness_ok=True,
        walkforward_ok=True,
        dsr_trial_accounting_ok=True,
        no_leakage=True,
        no_unknown_membership_traded=True,
        risk_config_valid=True,
        execution_config_valid=True,
        operator_approved_paper_session=True,
    )
    live = LiveTradingEligibilityGate().evaluate(
        certified_eligibility=decision.level.value,
        research_accepted=False,
        facts=facts,
        allow_live_send=False,
    )

    report = format_development_report(
        final_manifest,
        quality=qrep.to_dict(),
        research_eligibility=decision.level.value,
    )

    return DevelopmentIngestResult(
        success=True,
        root=written,
        manifest_path=written / "manifest.json",
        data_class=DATA_CLASS_DEVELOPMENT,
        research_eligibility=decision.level.value,
        research_eligible=False,
        paper_eligible=bool(paper.paper_eligible),
        live_eligible=bool(live.live_eligible),
        synthetic=final_manifest.synthetic,
        research_grade=False,
        real_orders=0,
        quality=qrep.to_dict(),
        report_text=report,
        blockers=list(decision.blockers) + list(paper.blockers) + list(live.blockers),
        facts=facts,
    )
