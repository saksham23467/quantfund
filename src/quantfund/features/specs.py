"""Feature specification contract."""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class FeatureSpec(BaseModel):
    """Declarative feature definition."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    feature_name: str
    version: str = "1.0.0"
    lookback: int
    required_columns: list[str]
    warmup_period: int
    output_columns: list[str]
    params: dict[str, Any] = Field(default_factory=dict)
    price_field: str = "adjusted"  # research default; execution remains RAW
    description: str = ""


FeatureFn = Callable[[pd.DataFrame, FeatureSpec], pd.DataFrame]
