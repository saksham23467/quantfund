"""Discover immutable Zerodha research packages — never invent contents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantfund.data.models import MarketBar
from quantfund.data.zerodha_hist.package import (
    load_bars_from_package,
    research_zerodha_root,
)


PREFERRED_SYMBOLS = (
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "ITC",
    "LT",
)


@dataclass(frozen=True)
class DiscoveredPackage:
    dataset_id: str
    dataset_version: str
    path: Path
    manifest: dict[str, Any]
    symbol: str
    bars: int
    start: str
    end: str
    content_hash: str
    price_policy: str
    eligibility: str


def _version_num(name: str) -> int:
    try:
        return int(name[1:]) if name.startswith("v") else -1
    except ValueError:
        return -1


def latest_version_dir(dataset_dir: Path) -> Path | None:
    if not dataset_dir.is_dir():
        return None
    versions = [p for p in dataset_dir.iterdir() if p.is_dir() and p.name.startswith("v")]
    if not versions:
        return None
    return max(versions, key=lambda p: _version_num(p.name))


def discover_zerodha_packages(
    *,
    root: Path | None = None,
    symbols: tuple[str, ...] | None = None,
) -> list[DiscoveredPackage]:
    """Discover latest package per symbol under data/research/zerodha."""
    root = root or research_zerodha_root()
    want = {s.upper() for s in (symbols or PREFERRED_SYMBOLS)}
    found: dict[str, DiscoveredPackage] = {}
    if not root.exists():
        return []

    for ds_dir in sorted(root.iterdir()):
        if not ds_dir.is_dir():
            continue
        ver = latest_version_dir(ds_dir)
        if ver is None:
            continue
        man_path = ver / "manifest.json"
        if not man_path.exists():
            continue
        man = json.loads(man_path.read_text(encoding="utf-8"))
        syms = [str(s).upper() for s in (man.get("symbols") or [])]
        if len(syms) != 1:
            continue
        sym = syms[0]
        if sym not in want:
            continue
        # Prefer longer date-range packages / higher row count for same symbol
        pkg = DiscoveredPackage(
            dataset_id=str(man.get("dataset_id") or ds_dir.name),
            dataset_version=str(man.get("dataset_version") or ver.name),
            path=ver,
            manifest=man,
            symbol=sym,
            bars=int(man.get("rows") or 0),
            start=str(man.get("start") or ""),
            end=str(man.get("end") or ""),
            content_hash=str(man.get("content_hash") or ""),
            price_policy=str(man.get("price_policy") or "unknown"),
            eligibility=str(man.get("eligibility") or "DEVELOPMENT_ONLY"),
        )
        prev = found.get(sym)
        if prev is None or pkg.bars > prev.bars:
            found[sym] = pkg
    # Stable order by preferred symbol list
    order = {s: i for i, s in enumerate(PREFERRED_SYMBOLS)}
    return sorted(found.values(), key=lambda p: order.get(p.symbol, 999))


def load_package_bars(pkg: DiscoveredPackage) -> list[MarketBar]:
    return load_bars_from_package(pkg.path)


def dataset_inventory(packages: list[DiscoveredPackage]) -> dict[str, Any]:
    return {
        "root": str(research_zerodha_root()),
        "package_count": len(packages),
        "symbols": [p.symbol for p in packages],
        "packages": [
            {
                "dataset_id": p.dataset_id,
                "dataset_version": p.dataset_version,
                "symbol": p.symbol,
                "bars": p.bars,
                "start": p.start,
                "end": p.end,
                "content_hash": p.content_hash,
                "price_policy": p.price_policy,
                "eligibility": p.eligibility,
                "provider": p.manifest.get("provider"),
                "source": p.manifest.get("source"),
                "path": str(p.path),
            }
            for p in packages
        ],
        "combined_hash_inputs": [p.content_hash for p in packages],
    }
