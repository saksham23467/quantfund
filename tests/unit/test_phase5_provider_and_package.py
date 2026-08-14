"""Phase 5 — provider capabilities, package validator, anti-forgery."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from quantfund.data.grades import SourceGrade
from quantfund.data.providers.capabilities import (
    yfinance_capabilities,
    synthetic_capabilities,
    unconfigured_research_capabilities,
)
from quantfund.data.providers.local_package import LocalResearchPackageProvider
from quantfund.data.providers.package_validator import validate_research_package
from quantfund.data.providers.roles import UnconfiguredResearchProvider

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "phase35" / "pilot_package"


def test_capability_declaration_required_fields():
    caps = yfinance_capabilities()
    assert caps.provider_id == "yfinance"
    assert caps.source_grade == SourceGrade.NON_EXCHANGE
    assert caps.license_status.value == "unknown"
    assert caps.attestation_hash().startswith("sha256:")


def test_unconfigured_research_provider_fail_closed():
    p = UnconfiguredResearchProvider()
    assert p.can_claim_research_eligible is False
    assert p.capabilities().can_satisfy_research_eligibility_source_bar() is False
    with pytest.raises(NotImplementedError):
        p.get_history("RELIANCE")


def test_provenance_present_on_local_package():
    p = LocalResearchPackageProvider(FIXTURE)
    prov = p.provenance()
    assert prov.provider
    assert prov.download_timestamp is not None
    assert prov.package_id


def test_synthetic_cannot_claim_exchange_via_capabilities():
    caps = synthetic_capabilities()
    assert caps.can_satisfy_research_eligibility_source_bar() is False
    assert caps.exchange_authority is False


def test_yfinance_cannot_claim_research_source_bar():
    caps = yfinance_capabilities()
    assert caps.can_satisfy_research_eligibility_source_bar() is False


def test_forged_exchange_grade_on_synthetic_package_rejected(tmp_path: Path):
    dest = tmp_path / "pkg"
    shutil.copytree(FIXTURE, dest)
    meta = json.loads((dest / "package.json").read_text(encoding="utf-8"))
    meta["source_grade"] = "exchange"
    meta["capabilities"]["exchange_authority"] = True
    (dest / "package.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    result = validate_research_package(dest)
    assert result.valid is False
    assert any(e.code == "forged_exchange_grade" for e in result.errors)


def test_eligibility_assertion_in_package_forbidden(tmp_path: Path):
    dest = tmp_path / "pkg"
    shutil.copytree(FIXTURE, dest)
    meta = json.loads((dest / "package.json").read_text(encoding="utf-8"))
    meta["research_eligible"] = True
    (dest / "package.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    result = validate_research_package(dest)
    assert result.valid is False
    assert any(e.code == "eligibility_assertion_forbidden" for e in result.errors)


def test_valid_synthetic_package_passes_validator():
    result = validate_research_package(FIXTURE)
    assert result.valid is True
    assert result.capabilities is not None
    assert result.capabilities.source_grade == SourceGrade.SYNTHETIC


def test_local_provider_refuses_invalid_package(tmp_path: Path):
    dest = tmp_path / "pkg"
    shutil.copytree(FIXTURE, dest)
    meta = json.loads((dest / "package.json").read_text(encoding="utf-8"))
    meta["source_grade"] = "exchange"
    (dest / "package.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        LocalResearchPackageProvider(dest)


def test_unconfigured_capabilities_helper():
    caps = unconfigured_research_capabilities()
    assert caps.provider_id == "unconfigured_research"
    assert caps.can_satisfy_research_eligibility_source_bar() is False
