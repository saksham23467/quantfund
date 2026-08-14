"""Project configuration and research defaults.

All cost and slippage values are configurable research assumptions,
not claims of exact current broker or exchange charges.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


def project_root() -> Path:
    """Return repository root (two levels above this package)."""
    return Path(__file__).resolve().parents[2]


class Paths(BaseModel):
    """Filesystem layout for data and experiment artifacts."""

    root: Path = Field(default_factory=project_root)
    data_dir: Path | None = None
    raw_dir: Path | None = None
    processed_dir: Path | None = None
    synthetic_dir: Path | None = None
    experiments_dir: Path | None = None

    normalized_dir: Path | None = None
    universes_dir: Path | None = None
    calendars_dir: Path | None = None
    datasets_dir: Path | None = None
    development_dir: Path | None = None
    registry_dir: Path | None = None

    def model_post_init(self, __context: object) -> None:
        base = Path(os.environ.get("QUANTFUND_DATA_DIR", self.root / "data"))
        experiments = Path(
            os.environ.get("QUANTFUND_EXPERIMENTS_DIR", self.root / "experiments")
        )
        object.__setattr__(self, "data_dir", base)
        object.__setattr__(self, "raw_dir", base / "raw")
        object.__setattr__(self, "processed_dir", base / "processed")
        object.__setattr__(self, "synthetic_dir", base / "synthetic")
        object.__setattr__(self, "normalized_dir", base / "normalized")
        object.__setattr__(self, "universes_dir", base / "universes")
        object.__setattr__(self, "calendars_dir", base / "calendars")
        object.__setattr__(self, "datasets_dir", base / "datasets")
        object.__setattr__(self, "development_dir", base / "development")
        object.__setattr__(self, "experiments_dir", experiments)
        object.__setattr__(self, "registry_dir", experiments / "registry")


def default_initial_capital() -> float:
    """Research paper/backtest capital in INR. Not for live automation."""
    return float(os.environ.get("QUANTFUND_INITIAL_CAPITAL", "100000"))


PATHS = Paths()
INITIAL_CAPITAL = default_initial_capital()
