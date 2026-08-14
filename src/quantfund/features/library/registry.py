"""Register built-in feature compute functions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantfund.features.specs import FeatureFn, FeatureSpec


def _ensure_sorted(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" not in df.columns:
        raise ValueError("feature input requires timestamp column")
    return df.sort_values("timestamp").reset_index(drop=True)


def compute_return_1(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = df["close"].pct_change(1)
    return out


def compute_log_return_1(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = np.log(df["close"]).diff(1)
    return out


def compute_rolling_return(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = df["close"].pct_change(n)
    return out


def compute_sma(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = df["close"].rolling(n, min_periods=n).mean()
    return out


def compute_ema(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = df["close"].ewm(span=n, adjust=False, min_periods=n).mean()
    return out


def compute_momentum(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = df["close"] / df["close"].shift(n) - 1.0
    return out


def compute_roc(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    return compute_momentum(df, spec)


def compute_rolling_vol(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    out = df[["timestamp"]].copy()
    rets = df["close"].pct_change()
    out[spec.output_columns[0]] = rets.rolling(n, min_periods=n).std()
    return out


def compute_atr(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = tr.rolling(n, min_periods=n).mean()
    return out


def compute_realized_vol(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    out = df[["timestamp"]].copy()
    logret = np.log(df["close"]).diff()
    out[spec.output_columns[0]] = logret.rolling(n, min_periods=n).std() * np.sqrt(252)
    return out


def compute_volume_change(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = df["volume"].pct_change(1)
    return out


def compute_relative_volume(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    out = df[["timestamp"]].copy()
    avg = df["volume"].rolling(n, min_periods=n).mean()
    out[spec.output_columns[0]] = df["volume"] / avg
    return out


def compute_dist_to_sma(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    sma = df["close"].rolling(n, min_periods=n).mean()
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = df["close"] / sma - 1.0
    return out


def compute_zscore(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    mean = df["close"].rolling(n, min_periods=n).mean()
    std = df["close"].rolling(n, min_periods=n).std()
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = (df["close"] - mean) / std.replace(0, np.nan)
    return out


def compute_benchmark_return(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    """Requires column benchmark_close on the frame."""
    df = _ensure_sorted(df)
    if "benchmark_close" not in df.columns:
        out = df[["timestamp"]].copy()
        out[spec.output_columns[0]] = np.nan
        return out
    out = df[["timestamp"]].copy()
    out[spec.output_columns[0]] = df["benchmark_close"].pct_change(1)
    return out


def compute_relative_strength(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    df = _ensure_sorted(df)
    n = int(spec.params["window"])
    out = df[["timestamp"]].copy()
    if "benchmark_close" not in df.columns:
        out[spec.output_columns[0]] = np.nan
        return out
    asset = df["close"] / df["close"].shift(n) - 1.0
    bench = df["benchmark_close"] / df["benchmark_close"].shift(n) - 1.0
    out[spec.output_columns[0]] = asset - bench
    return out


def make_spec(
    name: str,
    *,
    lookback: int,
    outputs: list[str],
    columns: list[str],
    params: dict | None = None,
    description: str = "",
) -> FeatureSpec:
    return FeatureSpec(
        feature_name=name,
        lookback=lookback,
        warmup_period=lookback,
        required_columns=columns,
        output_columns=outputs,
        params=params or {},
        description=description,
    )


def default_feature_registry() -> dict[str, tuple[FeatureSpec, FeatureFn]]:
    """Map feature_name -> (default spec template factory params, fn).

    Specs with window params are created by FeatureEngine.configure().
    """
    return {
        "return_1": (
            make_spec(
                "return_1",
                lookback=1,
                outputs=["return_1"],
                columns=["close"],
                description="1-bar simple return",
            ),
            compute_return_1,
        ),
        "log_return_1": (
            make_spec(
                "log_return_1",
                lookback=1,
                outputs=["log_return_1"],
                columns=["close"],
                description="1-bar log return",
            ),
            compute_log_return_1,
        ),
        "rolling_return": (None, compute_rolling_return),  # type: ignore[arg-type]
        "sma": (None, compute_sma),  # type: ignore[arg-type]
        "ema": (None, compute_ema),  # type: ignore[arg-type]
        "momentum": (None, compute_momentum),  # type: ignore[arg-type]
        "roc": (None, compute_roc),  # type: ignore[arg-type]
        "rolling_vol": (None, compute_rolling_vol),  # type: ignore[arg-type]
        "atr": (None, compute_atr),  # type: ignore[arg-type]
        "realized_vol": (None, compute_realized_vol),  # type: ignore[arg-type]
        "volume_change": (
            make_spec(
                "volume_change",
                lookback=1,
                outputs=["volume_change_1"],
                columns=["volume"],
            ),
            compute_volume_change,
        ),
        "relative_volume": (None, compute_relative_volume),  # type: ignore[arg-type]
        "dist_to_sma": (None, compute_dist_to_sma),  # type: ignore[arg-type]
        "zscore": (None, compute_zscore),  # type: ignore[arg-type]
        "benchmark_return": (
            make_spec(
                "benchmark_return",
                lookback=1,
                outputs=["benchmark_return_1"],
                columns=["benchmark_close"],
            ),
            compute_benchmark_return,
        ),
        "relative_strength": (None, compute_relative_strength),  # type: ignore[arg-type]
    }


def build_windowed_spec(name: str, window: int) -> FeatureSpec:
    mapping = {
        "rolling_return": ("rolling_return", [f"rolling_return_{window}"], ["close"]),
        "sma": ("sma", [f"sma_{window}"], ["close"]),
        "ema": ("ema", [f"ema_{window}"], ["close"]),
        "momentum": ("momentum", [f"momentum_{window}"], ["close"]),
        "roc": ("roc", [f"roc_{window}"], ["close"]),
        "rolling_vol": ("rolling_vol", [f"rolling_vol_{window}"], ["close"]),
        "atr": ("atr", [f"atr_{window}"], ["high", "low", "close"]),
        "realized_vol": ("realized_vol", [f"realized_vol_{window}"], ["close"]),
        "relative_volume": ("relative_volume", [f"relative_volume_{window}"], ["volume"]),
        "dist_to_sma": ("dist_to_sma", [f"dist_to_sma_{window}"], ["close"]),
        "zscore": ("zscore", [f"zscore_{window}"], ["close"]),
        "relative_strength": (
            "relative_strength",
            [f"relative_strength_{window}"],
            ["close", "benchmark_close"],
        ),
    }
    if name not in mapping:
        raise KeyError(name)
    fname, outputs, cols = mapping[name]
    return FeatureSpec(
        feature_name=fname,
        lookback=window,
        warmup_period=window,
        required_columns=cols,
        output_columns=outputs,
        params={"window": window},
    )
