"""Chronological train/validation/test splitting with TEST isolation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantfund.data.models import MarketBar


class SealedTestSetError(PermissionError):
    """Raised when development mode attempts to access the sealed TEST split."""


class Period(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: date
    end: date

    @model_validator(mode="after")
    def ordered(self) -> Period:
        if self.end < self.start:
            raise ValueError("period end must be >= start")
        return self


class SplitConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: str = "chronological"
    train: Period
    validation: Period
    test: Period
    embargo_sessions: int = 0
    purge_label_horizon: int = 0

    @model_validator(mode="after")
    def chronological_and_non_overlapping(self) -> SplitConfig:
        if self.method != "chronological":
            raise ValueError("only chronological splits are supported in Phase 2 v1")
        if not (
            self.train.end < self.validation.start
            and self.validation.end < self.test.start
        ):
            # Allow adjacent if end < next start (strict). Same-day overlap forbidden.
            raise ValueError(
                "train/validation/test must be strictly chronological and non-overlapping "
                "(train.end < validation.start < validation.end < test.start ordering)"
            )
        if self.validation.end >= self.test.start:
            raise ValueError("validation must end before test starts")
        if self.train.end >= self.validation.start:
            raise ValueError("train must end before validation starts")
        return self


@dataclass
class ChronologicalSplit:
    """Materialized bar splits with sealed TEST access control."""

    config: SplitConfig
    train_bars: list[MarketBar]
    validation_bars: list[MarketBar]
    test_bars: list[MarketBar]
    _test_unlocked: bool = False

    @classmethod
    def from_bars(cls, bars: list[MarketBar], config: SplitConfig) -> ChronologicalSplit:
        def in_period(b: MarketBar, p: Period) -> bool:
            d = b.timestamp.date() if isinstance(b.timestamp, datetime) else b.timestamp
            return p.start <= d <= p.end

        train = [b for b in bars if in_period(b, config.train)]
        val = [b for b in bars if in_period(b, config.validation)]
        test = [b for b in bars if in_period(b, config.test)]
        return cls(config=config, train_bars=train, validation_bars=val, test_bars=test)

    def unlock_test(self, *, sealed_evaluation: bool) -> None:
        """TEST may only be unlocked for a sealed final evaluation job."""
        if not sealed_evaluation:
            raise SealedTestSetError(
                "TEST split is sealed during development; set sealed_evaluation=True "
                "only for a pre-declared final evaluation"
            )
        self._test_unlocked = True

    def get_test_bars(self) -> list[MarketBar]:
        if not self._test_unlocked:
            raise SealedTestSetError("TEST split is sealed; call unlock_test first")
        return list(self.test_bars)

    def development_bars(self) -> list[MarketBar]:
        """Bars available during development: train + validation only."""
        return list(self.train_bars) + list(self.validation_bars)
