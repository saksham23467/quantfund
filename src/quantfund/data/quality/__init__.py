"""Data quality reporting and validation checks."""

from quantfund.data.quality.report import (
    QualityIssue,
    QualityReport,
    Severity,
)

__all__ = [
    "Severity",
    "QualityIssue",
    "QualityReport",
    "run_quality_checks",
]


def __getattr__(name: str):
    if name == "run_quality_checks":
        from quantfund.data.quality.checks import run_quality_checks

        return run_quality_checks
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
