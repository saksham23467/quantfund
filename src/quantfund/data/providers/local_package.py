"""Vendor-neutral local research data package adapter.

A package is a directory with package.json declaring capabilities/provenance
plus CSV/JSON payloads. This allows an NSE-grade or paid vendor export to be
plugged in without coupling FeatureEngine / Strategy / ResearchRunner /
BacktestEngine to a vendor SDK.

source_grade is read from package metadata — never inferred from "data looks OK".
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from quantfund.data.corporate_actions.models import CorporateAction
from quantfund.data.grades import SourceGrade
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.normalize import dataframe_to_bars
from quantfund.data.providers.capabilities import (
    CoverageQuality,
    LicenseStatus,
    ProviderCapabilities,
)
from quantfund.data.providers.package_validator import (
    PackageValidationResult,
    validate_research_package,
)
from quantfund.data.providers.provenance import ProvenanceRecord
from quantfund.data.providers.roles import ResearchProvider
from quantfund.data.validate import validate_bars


class LocalResearchPackageProvider(ResearchProvider):
    """Load a versioned on-disk research package."""

    def __init__(
        self,
        package_root: Path,
        *,
        validate: bool = True,
        allow_invalid: bool = False,
    ) -> None:
        self._root = Path(package_root)
        self._validation: PackageValidationResult | None = None
        if validate:
            self._validation = validate_research_package(self._root)
            if not self._validation.valid and not allow_invalid:
                self._validation.raise_if_invalid()
        meta_path = self._root / "package.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"package.json missing: {meta_path}")
        self._meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self._instruments = self._load_instruments()
        self._by_symbol = {i.symbol: i for i in self._instruments}
        self._by_id = {
            (i.instrument_id or i.symbol): i for i in self._instruments
        }
        self._actions = self._load_actions()
        self._terminal_events = self._load_terminal_events()
        self._bars_cache: dict[str, list[MarketBar]] = {}

    @property
    def name(self) -> str:
        return str(self._meta.get("provider", "local_research_package"))

    @property
    def source_grade(self) -> SourceGrade:
        return SourceGrade(self._meta["source_grade"])

    @property
    def validation(self) -> PackageValidationResult | None:
        return self._validation

    def capabilities(self) -> ProviderCapabilities:
        if self._validation and self._validation.capabilities is not None:
            return self._validation.capabilities
        c = self._meta.get("capabilities", {})
        lic_raw = str(
            self._meta.get("license_status") or c.get("license_status") or "unknown"
        )
        try:
            lic = LicenseStatus(lic_raw)
        except ValueError:
            lic = LicenseStatus.UNKNOWN
        return ProviderCapabilities(
            provider_id=str(self._meta.get("package_id", self.name)),
            provider_name=str(self._meta.get("provider_name", self.name)),
            source_grade=self.source_grade,
            historical_depth=str(c.get("historical_depth", "unknown")),
            corporate_action_quality=CoverageQuality(
                c.get("corporate_action_quality", "unknown")
            ),
            delisted_coverage=CoverageQuality(c.get("delisted_coverage", "unknown")),
            universe_membership_quality=CoverageQuality(
                c.get("universe_membership_quality", "unknown")
            ),
            identity_coverage=CoverageQuality(c.get("identity_coverage", "unknown")),
            exchange_authority=bool(
                self._meta.get("exchange_authority", c.get("exchange_authority", False))
            ),
            supports_instrument_master=bool(c.get("supports_instrument_master", True)),
            supports_symbol_isin_mapping=bool(
                c.get("supports_symbol_isin_mapping", True)
            ),
            supports_historical_identifiers=bool(
                c.get("supports_historical_identifiers", False)
            ),
            supports_daily_bars=bool(c.get("supports_daily_bars", True)),
            supports_corporate_actions=bool(c.get("supports_corporate_actions", False)),
            supports_pit_universe=bool(c.get("supports_pit_universe", False)),
            supports_delisted_instruments=bool(
                c.get("supports_delisted_instruments", False)
            ),
            supports_provenance=bool(c.get("supports_provenance", True)),
            supports_licensing_evidence=bool(
                c.get("supports_licensing_evidence", False)
            ),
            supported_exchanges=list(
                c.get("supported_exchanges") or self._meta.get("exchanges") or []
            ),
            supported_date_range=dict(c.get("supported_date_range") or {}),
            redistribution_allowed=c.get("redistribution_allowed"),
            license_status=lic,
            authority_evidence_refs=list(c.get("authority_evidence_refs") or []),
            licensing_notes=str(self._meta.get("licensing_notes", "")),
            usage_notes=str(self._meta.get("usage_notes", "")),
            limitations=list(self._meta.get("limitations", [])),
        )

    def license_evidence(self):
        if self._validation and self._validation.license_evidence is not None:
            return self._validation.license_evidence
        from quantfund.data.packages.license import parse_license_evidence

        lic_json = None
        lic_path = self._root / "LICENSE.json"
        if lic_path.exists():
            lic_json = json.loads(lic_path.read_text(encoding="utf-8"))
        return parse_license_evidence(
            package_meta=self._meta,
            license_json=lic_json,
            package_hash=self._validation.content_hash if self._validation else None,
        )

    def provenance(self) -> ProvenanceRecord:
        p = self._meta.get("provenance", {})
        # Optional sidecar provenance.json
        side = self._root / "provenance.json"
        if side.exists():
            p = {**p, **json.loads(side.read_text(encoding="utf-8"))}
        ts = p.get("download_timestamp") or self._meta.get("created_at")
        if isinstance(ts, str):
            download_ts = datetime.fromisoformat(ts)
        else:
            download_ts = datetime.now().astimezone()
        content_hashes = dict(p.get("content_hashes", {}))
        if self._validation and self._validation.content_hash:
            content_hashes.setdefault("package", self._validation.content_hash)
        le = self.license_evidence()
        acq_ts = le.acquisition_timestamp
        acq_dt = None
        if isinstance(acq_ts, str):
            try:
                acq_dt = datetime.fromisoformat(acq_ts)
            except ValueError:
                acq_dt = None
        return ProvenanceRecord(
            source=str(self._meta.get("source", self.name)),
            provider=self.name,
            download_timestamp=download_ts,
            request_parameters=dict(p.get("request_parameters", {})),
            source_identifiers=dict(p.get("source_identifiers", {})),
            content_hashes=content_hashes,
            coverage=dict(p.get("coverage", {})),
            limitations=list(self._meta.get("limitations", [])),
            license_ref=le.license_reference or self._meta.get("license_ref"),
            package_id=self._meta.get("package_id"),
            package_version=self._meta.get("package_version"),
            legal_source=le.legal_source,
            license_status=le.license_status.value,
            redistribution_allowed=le.redistribution_allowed,
            research_use_allowed=le.research_use_allowed,
            exchange_authority=le.exchange_authority,
            acquisition_method=le.acquisition_method,
            acquisition_timestamp=acq_dt,
            package_hash=le.package_hash
            or (self._validation.content_hash if self._validation else None),
        )

    def get_instruments(self) -> list[Instrument]:
        return list(self._instruments)

    def get_instrument_master(self) -> list[Instrument]:
        return list(self._instruments)

    def get_terminal_events(self) -> list:
        return list(self._terminal_events)

    def get_history(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[MarketBar]:
        if symbol not in self._bars_cache:
            path = self._root / "bars" / f"{symbol}.csv"
            if not path.exists():
                # Try instrument_id filename
                inst = self._by_symbol.get(symbol)
                if inst and inst.instrument_id:
                    alt = self._root / "bars" / f"{inst.instrument_id.replace(':', '_')}.csv"
                    path = alt if alt.exists() else path
            if not path.exists():
                return []
            df = pd.read_csv(path, parse_dates=["timestamp"])
            bars = validate_bars(dataframe_to_bars(df, symbol=symbol), require_non_empty=False)
            self._bars_cache[symbol] = bars
        bars = self._bars_cache[symbol]
        out = bars
        if start is not None:
            out = [b for b in out if b.timestamp >= start]
        if end is not None:
            out = [b for b in out if b.timestamp <= end]
        return out

    def get_corporate_actions(
        self,
        *,
        symbol: str | None = None,
        instrument_id: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[CorporateAction]:
        actions = list(self._actions)
        if symbol is not None:
            actions = [a for a in actions if a.symbol == symbol]
        if instrument_id is not None:
            actions = [a for a in actions if a.instrument_id == instrument_id]
        if start is not None:
            actions = [a for a in actions if a.ex_date >= start]
        if end is not None:
            actions = [a for a in actions if a.ex_date <= end]
        return actions

    def get_delisted_instruments(self) -> list[Instrument]:
        return [i for i in self._instruments if i.delisting_date is not None]

    def membership_path(self) -> Path | None:
        """Return package-local PIT membership file if present (no invent)."""
        from quantfund.data.packages.membership import discover_package_membership_path

        return discover_package_membership_path(self._root)

    def package_identity(self) -> str:
        """Deterministic identity from package_id, version, and content hash."""
        from quantfund.data.packages.vendor_import import deterministic_package_identity

        content_hash = (
            self._validation.content_hash
            if self._validation and self._validation.content_hash
            else "sha256:unknown"
        )
        return deterministic_package_identity(
            package_id=str(self._meta.get("package_id", "unknown")),
            package_version=str(self._meta.get("package_version", "unknown")),
            content_hash=content_hash,
        )

    def _load_instruments(self) -> list[Instrument]:
        path = self._root / "instruments.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Instrument.model_validate(row) for row in data]

    def _load_actions(self) -> list[CorporateAction]:
        path = self._root / "corporate_actions.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [CorporateAction.model_validate(row) for row in data]

    def _load_terminal_events(self) -> list:
        path = self._root / "terminal_events.json"
        if not path.exists():
            return []
        from quantfund.data.instruments.delisted import TerminalEvent

        data = json.loads(path.read_text(encoding="utf-8"))
        return [TerminalEvent.model_validate(row) for row in data]
