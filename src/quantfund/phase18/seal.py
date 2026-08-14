"""Code-level TEST seal for Phase 18 ranking (no TEST in selection)."""

from __future__ import annotations

from typing import Any


class SealViolation(RuntimeError):
    """Raised when TEST metrics are used for ranking / parameter selection."""


# Alias kept for clarity in call sites; avoid pytest Test* collection.
class SealGuard:
    """Tracks whether TEST metrics may be read.

    Screening / ranking must call ``assert_can_rank`` and only consume
    train/validation metrics. Finalist evaluation unlocks TEST explicitly.
    """

    def __init__(self) -> None:
        self._test_unlocked = False
        self._test_reads = 0
        self._ranking_reads_blocked = 0

    @property
    def test_unlocked(self) -> bool:
        return self._test_unlocked

    def unlock_for_final_evaluation(self) -> None:
        self._test_unlocked = True

    def extract_ranking_metrics(self, metrics_by_split: dict[str, Any]) -> dict[str, Any]:
        """Return only train/validation for ranking. Never returns TEST."""
        out = {
            "train": dict(metrics_by_split.get("train") or {}),
            "validation": dict(metrics_by_split.get("validation") or {}),
        }
        # Prove TEST is not used even if present
        if "test" in metrics_by_split and not self._test_unlocked:
            test = metrics_by_split.get("test") or {}
            if test.get("sealed") is True or test.get("accessible") is False:
                pass  # sealed marker ok
            elif any(k in test for k in ("sharpe_ratio", "cagr", "total_return")):
                self._ranking_reads_blocked += 1
                # Do not copy into ranking payload
        return out

    def extract_test_metrics(self, metrics_by_split: dict[str, Any]) -> dict[str, Any]:
        if not self._test_unlocked:
            raise SealViolation(
                "TEST metrics inaccessible until final sealed evaluation"
            )
        self._test_reads += 1
        return dict(metrics_by_split.get("test") or {})

    def assert_can_rank(self, payload: dict[str, Any]) -> None:
        if "test" in payload or "test_metrics" in payload:
            # Allow sealed markers only
            tm = payload.get("test_metrics") or payload.get("test") or {}
            if isinstance(tm, dict) and (
                tm.get("sealed") is True or tm.get("accessible") is False
            ):
                return
            if isinstance(tm, dict) and any(
                k in tm for k in ("sharpe_ratio", "cagr", "total_return")
            ):
                raise SealViolation("ranking payload must not include TEST metrics")

    def status(self) -> dict[str, Any]:
        return {
            "test_unlocked": self._test_unlocked,
            "test_reads_after_unlock": self._test_reads,
            "ranking_test_blocks": self._ranking_reads_blocked,
            "policy": "sealed_until_finalists",
        }
