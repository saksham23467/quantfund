"""Shared source-grade vocabulary (kept free of import cycles)."""

from __future__ import annotations

from enum import Enum


class SourceGrade(str, Enum):
    NON_EXCHANGE = "non_exchange"
    EXCHANGE = "exchange"
    PAID = "paid"
    SYNTHETIC = "synthetic"
