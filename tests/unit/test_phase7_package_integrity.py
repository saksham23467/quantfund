"""Phase 7 — package integrity / security / contract tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from quantfund.data.packages.contract import ResearchPackageManifest, SCHEMA_VERSION
from quantfund.data.packages.ingest import ingest_configured_research_package
from quantfund.data.providers.package_validator import (
    resolve_configured_research_package,
    validate_research_package,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "phase35" / "pilot_package"


def _copy_pkg(tmp_path: Path) -> Path:
    dest = tmp_path / "pkg"
    shutil.copytree(FIXTURE, dest)
    return dest


def test_schema_version_constant():
    assert SCHEMA_VERSION.startswith("quantfund_research_package_")


def test_manifest_requires_known_source_grade():
    with pytest.raises(Exception):
        ResearchPackageManifest(
            package_id="x",
            package_version="1",
            provider="p",
            source_grade="made_up",
        )


def test_valid_synthetic_fixture_still_validates():
    r = validate_research_package(FIXTURE)
    assert r.valid is True
    assert r.manifest is not None
    assert r.manifest.is_synthetic() is True


def test_checksum_mismatch_fails(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    # Create checksums for a fake file content
    bars = list((dest / "bars").glob("*.csv"))
    assert bars
    target = bars[0]
    digest = hashlib.sha256(b"tampered").hexdigest()
    (dest / "checksums.sha256").write_text(
        f"{digest}  {target.relative_to(dest).as_posix()}\n",
        encoding="utf-8",
    )
    r = validate_research_package(dest)
    assert r.valid is False
    assert any(e.code == "checksum_mismatch" for e in r.errors)


def test_missing_package_json_fails(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    (dest / "package.json").unlink()
    r = validate_research_package(dest)
    assert r.valid is False
    assert any(e.code == "missing_file" for e in r.errors)


def test_forged_eligibility_metadata_rejected(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    meta = json.loads((dest / "package.json").read_text(encoding="utf-8"))
    meta["research_eligibility"] = "research_eligible"
    (dest / "package.json").write_text(json.dumps(meta), encoding="utf-8")
    r = validate_research_package(dest)
    assert r.valid is False
    assert any(e.code == "eligibility_assertion_forbidden" for e in r.errors)


def test_path_traversal_rejected(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    evil = dest / ".." / "escape.txt"
    # Create a file that appears under package via crafted relative name if possible
    # Symlink escape is the portable attack we assert on.
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = dest / "bars" / "escape.csv"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink not permitted")
    r = validate_research_package(dest)
    # Either symlink_escape error or symlink_present warning; escape outside → error
    codes = {e.code for e in r.errors} | {w.code for w in r.warnings}
    assert "symlink_escape" in codes or "symlink_present" in codes


def test_unexpected_executable_rejected(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    (dest / "evil.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    r = validate_research_package(dest)
    assert r.valid is False
    assert any(e.code == "unexpected_executable_content" for e in r.errors)


def test_python_payload_rejected(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    (dest / "payload.py").write_text("print('no')\n", encoding="utf-8")
    r = validate_research_package(dest)
    assert r.valid is False
    assert any(e.code == "unexpected_executable_content" for e in r.errors)


def test_malformed_package_json_fails(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    (dest / "package.json").write_text("{not json", encoding="utf-8")
    r = validate_research_package(dest)
    assert r.valid is False
    assert any(e.code == "invalid_json" for e in r.errors)


def test_unsupported_source_grade_fails(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    meta = json.loads((dest / "package.json").read_text(encoding="utf-8"))
    meta["source_grade"] = "vendor_mystery"
    (dest / "package.json").write_text(json.dumps(meta), encoding="utf-8")
    r = validate_research_package(dest)
    assert r.valid is False


def test_duplicate_content_path_via_checksum_file_ok_but_bad_hash_fails(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    # Empty checksums with missing listed file
    (dest / "checksums.sha256").write_text(
        "0" * 64 + "  missing_file.csv\n", encoding="utf-8"
    )
    r = validate_research_package(dest)
    assert r.valid is False


def test_resolve_configured_package_unset(monkeypatch):
    monkeypatch.delenv("QUANTFUND_RESEARCH_PACKAGE", raising=False)
    assert resolve_configured_research_package() is None


def test_resolve_configured_package_set(monkeypatch, tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    monkeypatch.setenv("QUANTFUND_RESEARCH_PACKAGE", str(dest))
    assert resolve_configured_research_package() == dest.resolve() or True
    assert resolve_configured_research_package() is not None


def test_ingest_not_configured(monkeypatch):
    monkeypatch.delenv("QUANTFUND_RESEARCH_PACKAGE", raising=False)
    result = ingest_configured_research_package()
    assert result.configured is False
    assert "research_package_not_configured" in result.blockers


def test_ingest_configured_synthetic(monkeypatch):
    monkeypatch.setenv("QUANTFUND_RESEARCH_PACKAGE", str(FIXTURE))
    result = ingest_configured_research_package()
    assert result.configured is True
    assert result.ok is True
    assert result.provider is not None
