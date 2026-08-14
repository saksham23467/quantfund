"""Explicit mode manifest for real-market-data paper trading.

Three invariants are declared here and enforced everywhere downstream:

    DATA_SOURCE     = ZERODHA
    EXECUTION_MODE  = PAPER
    BROKER_WRITES   = DISABLED

These are not toggles. ``EXECUTION_MODE`` may only ever be ``PAPER`` in this
module, and ``BROKER_WRITES`` may only ever be ``DISABLED``. Constructing a
manifest with any other value raises immediately (fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DataSource(str, Enum):
    ZERODHA = "ZERODHA"


class ExecutionMode(str, Enum):
    PAPER = "PAPER"


class BrokerWrites(str, Enum):
    DISABLED = "DISABLED"


# Canonical constants (mirrored into every report).
DATA_SOURCE = DataSource.ZERODHA
EXECUTION_MODE = ExecutionMode.PAPER
BROKER_WRITES = BrokerWrites.DISABLED


@dataclass(frozen=True)
class PaperModeManifest:
    """Immutable declaration of the run mode. Real broker writes impossible."""

    data_source: DataSource = DATA_SOURCE
    execution_mode: ExecutionMode = EXECUTION_MODE
    broker_writes: BrokerWrites = BROKER_WRITES

    def __post_init__(self) -> None:
        if self.execution_mode is not ExecutionMode.PAPER:
            raise ValueError("execution_mode must be PAPER in paper_realdata")
        if self.broker_writes is not BrokerWrites.DISABLED:
            raise ValueError("broker_writes must be DISABLED in paper_realdata")
        if self.data_source is not DataSource.ZERODHA:
            raise ValueError("data_source must be ZERODHA in paper_realdata")

    def to_dict(self) -> dict[str, str]:
        return {
            "DATA_SOURCE": self.data_source.value,
            "EXECUTION_MODE": self.execution_mode.value,
            "BROKER_WRITES": self.broker_writes.value,
        }


# The intended data → execution → portfolio pipeline (documentation of wiring).
ARCHITECTURE = (
    "Zerodha market data",
    "market-data adapter",
    "strategy",
    "risk engine",
    "PaperExecutionAdapter",
    "simulated fills",
    "paper portfolio",
)
