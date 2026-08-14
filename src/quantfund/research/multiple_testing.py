"""Multiple-testing accounting and Deflated Sharpe Ratio (DSR)."""

from __future__ import annotations

import math
from typing import Any


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def deflated_sharpe_ratio(
    sharpe: float | None,
    *,
    n_obs: int,
    n_trials: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    benchmark_sharpe: float = 0.0,
) -> float | None:
    """Bailey & López de Prado Deflated Sharpe Ratio (simplified).

    Returns probability that observed Sharpe exceeds the expected max Sharpe
    under n_trials independent tests. None if undefined.
    """
    if sharpe is None or n_obs < 2 or n_trials < 1:
        return None
    # Variance of Sharpe estimator (non-normal adjustment)
    sr_var = (
        1.0
        - skew * sharpe
        + ((kurtosis - 1.0) / 4.0) * sharpe**2
    ) / (n_obs - 1)
    if sr_var <= 0:
        return None
    sr_std = math.sqrt(sr_var)
    # Expected max Sharpe under n_trials ~ benchmark + sr_std * z
    # Approximation: E[max Z] ≈ (1-γ)*Φ^{-1}(1-1/n) + γ*Φ^{-1}(1-1/(n*e))
    # Use simple inverse-norm approximation via binary search
    gamma = 0.5772156649
    if n_trials == 1:
        e_max = benchmark_sharpe
    else:
        z1 = _inv_norm(1.0 - 1.0 / n_trials)
        z2 = _inv_norm(1.0 - 1.0 / (n_trials * math.e))
        e_max = benchmark_sharpe + sr_std * ((1 - gamma) * z1 + gamma * z2)
    z = (sharpe - e_max) / sr_std
    return float(_norm_cdf(z))


def _inv_norm(p: float) -> float:
    """Approximate inverse standard normal CDF (Beasley-Springer/Moro style lite)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p must be in (0,1)")
    # Rational approximation for central region
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (
            ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(
            ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
    ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def trial_accounting_payload(counts: dict[str, int], selection_criterion: str) -> dict[str, Any]:
    return {
        "n_experiments": counts.get("n_experiments", 0),
        "n_param_combinations": counts.get("n_param_combinations", 0),
        "n_strategies_tested": counts.get("n_strategies", 0),
        "selection_criterion": selection_criterion,
    }
