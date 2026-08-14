"""Build versioned development/research datasets from RAW downloads."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.certification import (
    certify,
    facts_from_manifest_and_quality,
    write_certification,
)
from quantfund.data.corporate_actions.adjust import apply_adjustment_policy
from quantfund.data.corporate_actions.coverage import derive_ca_coverage_report
from quantfund.data.corporate_actions.models import CorporateAction
from quantfund.data.corporate_actions.policies import AdjustmentPolicy, default_split_bonus_policy
from quantfund.data.datasets.manifest import (
    DEVELOPMENT_WARNING,
    DatasetKind,
    DatasetManifest,
    ResearchEligibility,
    SourceGrade,
)
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.ingest.checksums import directory_checksum, hash_json, verify_checksums
from quantfund.data.ingest.pipeline import load_raw_bars
from quantfund.data.instruments.coverage import measure_delisted_coverage
from quantfund.data.instruments.delisted import TerminalEvent, compute_delisted_coverage
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.policy import DelistedCoverage, EligibilityLevel
from quantfund.data.providers.capabilities import ProviderCapabilities
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.quality.report import QualityReport
from quantfund.data.universe.coverage import compute_membership_coverage
from quantfund.data.universe.models import UniverseCompleteness, UniverseVersion


def _source_grade_for(source: str, explicit: SourceGrade | None = None) -> SourceGrade:
    if explicit is not None:
        return explicit
    if source == "yfinance":
        return SourceGrade.NON_EXCHANGE
    if source == "synthetic":
        return SourceGrade.SYNTHETIC
    return SourceGrade.NON_EXCHANGE


class DatasetBuilder:
    """Construct immutable dataset versions under data/datasets/."""

    def __init__(self, datasets_root: Path) -> None:
        self.datasets_root = Path(datasets_root)

    def dataset_path(self, dataset_id: str, dataset_version: str) -> Path:
        return self.datasets_root / dataset_id / dataset_version

    def build(
        self,
        *,
        dataset_id: str,
        dataset_version: str,
        bars: list[MarketBar],
        universe: UniverseVersion,
        calendar: CalendarProvider,
        actions: list[CorporateAction] | None = None,
        policy: AdjustmentPolicy | None = None,
        source: str,
        download_id: str,
        download_timestamp: datetime | None = None,
        raw_root: Path | None = None,
        source_grade: SourceGrade | None = None,
        fail_on_quality_errors: bool = True,
        instruments: list[Instrument] | None = None,
        terminal_events: list[TerminalEvent] | None = None,
        delisted_coverage: str | None = None,
        provider_capabilities: ProviderCapabilities | None = None,
        package_content_hash: str | None = None,
        license_status: str = "unknown",
        provenance_complete: bool = False,
        eligibility_checker: ResearchEligibilityChecker | None = None,
    ) -> tuple[DatasetManifest, QualityReport]:
        """Validate → adjust (derived cols) → write partitioned Parquet + manifest.

        RAW OHLC columns are written unchanged. Adjusted columns are additive.
        """
        out = self.dataset_path(dataset_id, dataset_version)
        if out.exists():
            raise FileExistsError(
                f"Dataset version already exists (immutable): {out}. "
                "Create a new dataset_version for new transformations."
            )

        policy = policy or default_split_bonus_policy()
        actions = actions or []
        grade = _source_grade_for(source, source_grade)
        download_timestamp = download_timestamp or datetime.now(timezone.utc)
        ca_report = derive_ca_coverage_report(actions, source_grade=grade.value)
        ca_coverage = ca_report.overall

        raw_checksum = None
        if raw_root is not None:
            if not verify_checksums(raw_root):
                raise ValueError(f"Raw checksum verification failed for {raw_root}")
            raw_checksum = directory_checksum(raw_root)

        quality = run_quality_checks(
            bars,
            calendar=calendar,
            universe=universe,
            actions=actions,
            instruments=instruments,
            terminal_events=terminal_events,
            provider_capabilities=provider_capabilities,
            expected_package_hash=package_content_hash,
            observed_package_hash=package_content_hash,
            dataset_id=dataset_id,
            source=source,
        )
        quality.adjustment_policy = policy.to_manifest_dict()
        if fail_on_quality_errors:
            quality.raise_if_errors()

        # Coverage metrics (evidence for certification facts)
        d0 = date.fromisoformat(quality.date_range_start) if quality.date_range_start else None
        d1 = date.fromisoformat(quality.date_range_end) if quality.date_range_end else None
        membership_ratio = None
        if d0 and d1:
            cov = compute_membership_coverage(
                universe,
                calendar=calendar,
                start=d0,
                end=d1,
                symbols=sorted({b.symbol for b in bars}),
            )
            membership_ratio = cov.membership_coverage_ratio
            # Prefer full coverage count for unknown sessions when available
            if cov.unknown_membership_sessions > quality.unknown_membership_periods:
                quality.unknown_membership_periods = cov.unknown_membership_sessions

        delisted_report = measure_delisted_coverage(
            instruments=instruments or [],
            events=terminal_events,
            coverage_start=d0,
            coverage_end=d1,
        )
        if delisted_coverage is None:
            # Prefer measurable report level; keep legacy helper as fallback
            delisted_coverage = delisted_report.level or compute_delisted_coverage(
                instruments=instruments or [],
                events=terminal_events,
            )

        capability_source_bar_ok = False
        capability_attestation_hash = None
        if provider_capabilities is not None:
            capability_source_bar_ok = (
                provider_capabilities.can_satisfy_research_eligibility_source_bar()
            )
            capability_attestation_hash = provider_capabilities.attestation_hash()
            if provider_capabilities.license_status.value != "unknown":
                license_status = provider_capabilities.license_status.value
        synthetic_flag = grade == SourceGrade.SYNTHETIC or source in {
            "yfinance",
            "synthetic",
            "synthetic_fixture",
            "phase35_synthetic_pilot",
        }
        # Synthetic / yfinance paths can never pass source bar
        if grade in {SourceGrade.SYNTHETIC, SourceGrade.NON_EXCHANGE} or source in {
            "yfinance",
            "synthetic",
            "synthetic_fixture",
            "phase35_synthetic_pilot",
        }:
            capability_source_bar_ok = False

        adjusted = apply_adjustment_policy(bars, actions, policy)

        # Write symbol-partitioned parquet
        out.mkdir(parents=True, exist_ok=False)
        bars_root = out / "bars"
        by_symbol: dict[str, list] = {}
        for item in adjusted:
            by_symbol.setdefault(item.raw.symbol, []).append(item)

        for symbol, items in sorted(by_symbol.items()):
            part_dir = bars_root / f"symbol={symbol}"
            part_dir.mkdir(parents=True, exist_ok=True)
            rows = []
            for item in items:
                b = item.raw
                rows.append(
                    {
                        "timestamp": b.timestamp,
                        "symbol": b.symbol,
                        "open": b.open,
                        "high": b.high,
                        "low": b.low,
                        "close": b.close,
                        "volume": b.volume,
                        "adj_open": item.adj_open,
                        "adj_high": item.adj_high,
                        "adj_low": item.adj_low,
                        "adj_close": item.adj_close,
                        "adjustment_factor": item.adjustment_factor,
                    }
                )
            pd.DataFrame(rows).to_parquet(part_dir / "part.parquet", index=False)

        # Dividends tracked separately
        div_rows = [
            a.model_dump(mode="json")
            for a in actions
            if a.action_type.value == "dividend"
        ]
        (out / "dividends.json").write_text(json.dumps(div_rows, indent=2), encoding="utf-8")
        (out / "corporate_actions.json").write_text(
            json.dumps([a.model_dump(mode="json") for a in actions], indent=2),
            encoding="utf-8",
        )
        (out / "universe.json").write_text(
            json.dumps(universe.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        (out / "adjustment_policy.json").write_text(
            json.dumps(policy.to_manifest_dict(), indent=2), encoding="utf-8"
        )

        quality_path = out / "quality_report.json"
        # content hash over bar partitions (deterministic)
        content_hash = directory_checksum(bars_root)

        cal_meta = calendar.metadata()

        # Provisional eligibility; ResearchEligibilityChecker + manifest gates win.
        eligibility = ResearchEligibility.DEVELOPMENT_ONLY
        kind = DatasetKind.DEVELOPMENT
        status = "development"
        if (
            grade in {SourceGrade.EXCHANGE, SourceGrade.PAID}
            and universe.completeness
            in {UniverseCompleteness.PARTIAL_PIT, UniverseCompleteness.FULL_PIT}
            and calendar.verified
        ):
            eligibility = ResearchEligibility.EXPLORATORY
            kind = DatasetKind.RESEARCH
            status = "research"

        warnings = list(universe.warnings)
        if grade == SourceGrade.NON_EXCHANGE or source == "yfinance":
            warnings = [DEVELOPMENT_WARNING, *warnings]

        lineage = {
            "source": source,
            "download_id": download_id,
            "raw_root": str(raw_root) if raw_root else None,
            "raw_checksum": raw_checksum,
            "normalization": "marketbar_v1",
            "corporate_action_policy": policy.policy_id,
            "corporate_action_coverage": ca_coverage,
            "ca_coverage_breakdown": ca_report.to_dict(),
            "delisted_coverage": delisted_coverage,
            "membership_coverage_ratio": membership_ratio,
            "capability_source_bar_ok": capability_source_bar_ok,
            "capability_attestation_hash": capability_attestation_hash,
            "package_content_hash": package_content_hash,
            "provenance_complete": provenance_complete,
            "license_status": license_status,
            "delisted_coverage_report": delisted_report.to_dict(),
            "synthetic": synthetic_flag,
            "universe_id": universe.universe_id,
            "universe_version": universe.universe_version,
            "calendar_id": calendar.calendar_id,
            "calendar_version": calendar.calendar_version,
            "calendar_verified": calendar.verified,
            "calendar_content_hash": cal_meta.content_hash,
            "calendar_source": cal_meta.source,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "quality_error_count": quality.error_count,
            "quality_warning_count": quality.warning_count,
        }

        # Write calendar metadata alongside dataset for auditability
        (out / "calendar_metadata.json").write_text(
            json.dumps(cal_meta.to_manifest_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        manifest = DatasetManifest(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            dataset_kind=kind,
            research_eligibility=eligibility,
            source=source,
            source_grade=grade,
            dataset_status=status,
            download_id=download_id,
            download_timestamp=download_timestamp,
            date_range_start=quality.date_range_start or "",
            date_range_end=quality.date_range_end or "",
            frequency="1d",
            universe_id=universe.universe_id,
            universe_version=universe.universe_version,
            universe_completeness=universe.completeness,
            calendar_id=calendar.calendar_id,
            calendar_version=calendar.calendar_version,
            calendar_verified=calendar.verified,
            calendar_content_hash=cal_meta.content_hash,
            calendar_source=cal_meta.source,
            adjustment_policy=policy.to_manifest_dict(),
            content_hash=content_hash,
            bar_count=len(bars),
            instrument_count=len(by_symbol),
            raw_checksum=raw_checksum,
            quality_report_path=str(quality_path),
            lineage=lineage,
            warnings=warnings,
            notes=(
                "Execution must use RAW OHLC. "
                "Adjusted columns are for research continuity only."
            ),
        )

        def _facts(m: DatasetManifest):
            return facts_from_manifest_and_quality(
                manifest=m,
                quality=quality,
                corporate_action_coverage=ca_coverage,
                delisted_coverage=delisted_coverage or DelistedCoverage.UNKNOWN.value,
                membership_coverage_ratio=membership_ratio,
                capability_source_bar_ok=capability_source_bar_ok,
                provenance_complete=provenance_complete,
                license_status=license_status,
                capability_attestation_hash=capability_attestation_hash,
                package_content_hash=package_content_hash,
                ca_coverage_breakdown=ca_report.to_dict(),
                extras={
                    "synthetic": synthetic_flag,
                    "delisted_coverage_report": delisted_report.to_dict(),
                    "source_grade": grade.value,
                    "exchange_authority": bool(
                        provider_capabilities.exchange_authority
                        if provider_capabilities
                        else False
                    ),
                    "research_eligibility": "derived",
                },
            )

        # Central eligibility gate — cannot be overridden by provisional labels.
        facts = _facts(manifest)
        decision = certify(facts, checker=eligibility_checker)
        level_to_eligibility = {
            EligibilityLevel.DEVELOPMENT_ONLY: ResearchEligibility.DEVELOPMENT_ONLY,
            EligibilityLevel.RESEARCH_ELIGIBLE: ResearchEligibility.RESEARCH_ELIGIBLE,
            EligibilityLevel.PRODUCTION_CANDIDATE: ResearchEligibility.PRODUCTION_CANDIDATE,
        }
        eligibility = level_to_eligibility[decision.level]
        kind = (
            DatasetKind.DEVELOPMENT
            if eligibility == ResearchEligibility.DEVELOPMENT_ONLY
            else DatasetKind.RESEARCH
        )
        status = "development" if kind == DatasetKind.DEVELOPMENT else "research"
        payload = manifest.model_dump(mode="json")
        payload["research_eligibility"] = eligibility.value
        payload["dataset_kind"] = kind.value
        payload["dataset_status"] = status
        # Manifest gates re-applied (e.g. non_exchange still forces development_only)
        manifest = DatasetManifest.model_validate(payload)
        final_facts = _facts(manifest)
        final_decision = certify(final_facts, checker=eligibility_checker)

        quality_path.write_text(
            json.dumps(quality.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        (out / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        write_certification(
            out / "certification.txt",
            facts=final_facts,
            decision=final_decision,
        )
        # Fingerprint for reproducibility checks (manifest without wall-clock noise)
        fingerprint = {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "content_hash": content_hash,
            "adjustment_policy": policy.to_manifest_dict(),
            "universe_version": universe.universe_version,
            "calendar_version": calendar.calendar_version,
            "source": source,
            "corporate_action_coverage": ca_coverage,
        }
        (out / "fingerprint.json").write_text(
            json.dumps({"fingerprint": hash_json(fingerprint), "payload": fingerprint}, indent=2),
            encoding="utf-8",
        )
        return manifest, quality


def build_from_raw(
    builder: DatasetBuilder,
    *,
    raw_root: Path,
    dataset_id: str,
    dataset_version: str,
    universe: UniverseVersion,
    calendar: CalendarProvider,
    actions: list[CorporateAction] | None = None,
    policy: AdjustmentPolicy | None = None,
    source: str,
    download_id: str,
    fail_on_quality_errors: bool = True,
) -> tuple[DatasetManifest, QualityReport]:
    bars = load_raw_bars(raw_root)
    return builder.build(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        bars=bars,
        universe=universe,
        calendar=calendar,
        actions=actions,
        policy=policy,
        source=source,
        download_id=download_id,
        raw_root=raw_root,
        fail_on_quality_errors=fail_on_quality_errors,
    )
