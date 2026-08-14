"""Persist DEVELOPMENT_DATA under data/development/ (not research packages)."""

from __future__ import annotations

import json
from pathlib import Path

from quantfund.config import PATHS
from quantfund.data.development.manifest import DevelopmentManifest
from quantfund.data.ingest.checksums import directory_checksum
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.normalize import bars_to_dataframe


def development_dataset_root(
    *,
    dataset_id: str,
    dataset_version: str,
    base: Path | None = None,
) -> Path:
    root = Path(base) if base is not None else Path(PATHS.development_dir)  # type: ignore[arg-type]
    return root / "india_eq" / dataset_id / dataset_version


def write_development_dataset(
    *,
    root: Path,
    bars: list[MarketBar],
    instruments: list[Instrument],
    manifest: DevelopmentManifest,
) -> Path:
    root = Path(root)
    if root.exists():
        raise FileExistsError(f"development dataset already exists: {root}")
    bars_dir = root / "bars"
    meta_dir = root / "metadata"
    bars_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)

    by_symbol: dict[str, list[MarketBar]] = {}
    for b in bars:
        by_symbol.setdefault(b.symbol, []).append(b)
    for symbol, sym_bars in by_symbol.items():
        df = bars_to_dataframe(sorted(sym_bars, key=lambda x: x.timestamp))
        df.to_csv(bars_dir / f"{symbol}.csv", index=False)

    (root / "instruments.json").write_text(
        json.dumps([i.model_dump(mode="json") for i in instruments], indent=2),
        encoding="utf-8",
    )
    (meta_dir / "coverage.json").write_text(
        json.dumps(
            {
                "pit_membership": manifest.pit_membership,
                "universe_mode": manifest.universe_mode,
                "corporate_action_coverage": manifest.corporate_action_coverage,
                "delisted_coverage": manifest.delisted_coverage,
                "note": "DEVELOPMENT_DATA — not research-grade",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Write manifest without final hash first, then recompute
    provisional = manifest.model_copy(
        update={"content_hash": "sha256:pending"}
    )
    provisional.write(root / "manifest.json")
    content_hash = directory_checksum(root)
    final = manifest.model_copy(update={"content_hash": content_hash})
    final.write(root / "manifest.json")
    return root


def load_development_manifest(root: Path) -> DevelopmentManifest:
    return DevelopmentManifest.model_validate(
        json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))
    )
