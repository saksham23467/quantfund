"""Apply AdjustmentPolicy to produce adjusted columns without mutating RAW OHLC.

Mathematics (split/bonus backward adjustment)
---------------------------------------------
For each split/bonus with ex-date T and factor r = ratio_num / ratio_den
(e.g. 2-for-1 ⇒ r = 2):

Define cumulative factor C(t) as the product of all r with ex_date > t
(i.e. actions that occur strictly after session t).

Then:
    P_adj(t) = P_raw(t) / C(t)

for P in {open, high, low, close}.

Volume may optionally be scaled as V_adj(t) = V_raw(t) * C(t); Phase 1 stores
adjustment_factor = C(t) and adj_* price columns; volume remains RAW.

Dividends are NOT applied to OHLC when policy.adjust_dividends_in_ohlc is False.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.corporate_actions.policies import AdjustmentPolicy
from quantfund.data.models import MarketBar


@dataclass(frozen=True)
class AdjustedBar:
    """Bar with RAW OHLC preserved and optional adjusted fields."""

    raw: MarketBar
    adj_open: float | None
    adj_high: float | None
    adj_low: float | None
    adj_close: float | None
    adjustment_factor: float
    dividends: tuple[CorporateAction, ...]


def _session_date(ts: datetime) -> date:
    return ts.date() if isinstance(ts, datetime) else ts


def _cumulative_factor(
    session: date,
    actions: list[CorporateAction],
    policy: AdjustmentPolicy,
) -> float:
    factor = 1.0
    for action in actions:
        if action.ex_date <= session:
            continue
        # SPLIT covers forward and reverse splits (ratio_num/ratio_den < 1 ⇒ reverse).
        if action.action_type == CorporateActionType.SPLIT and policy.adjust_splits:
            r = action.split_factor
            if r is not None:
                factor *= r
        elif action.action_type == CorporateActionType.BONUS and policy.adjust_bonus:
            r = action.split_factor
            if r is not None:
                factor *= r
        # SYMBOL_CHANGE / DIVIDEND / MERGER / DEMERGER do not alter OHLC here.
    return factor


def apply_adjustment_policy(
    bars: list[MarketBar],
    actions: list[CorporateAction],
    policy: AdjustmentPolicy,
) -> list[AdjustedBar]:
    """Return adjusted bars. Never mutates input MarketBar objects."""
    if not bars:
        return []

    # Reject automatic merger/demerger reconstruction.
    for action in actions:
        if action.requires_manual_treatment and action.action_type in {
            CorporateActionType.MERGER,
            CorporateActionType.DEMERGER,
        }:
            # Allowed in ledger; no transformation invented here.
            continue

    dividends_by_date: dict[date, list[CorporateAction]] = {}
    for action in actions:
        if action.action_type == CorporateActionType.DIVIDEND and policy.track_dividends_separately:
            dividends_by_date.setdefault(action.ex_date, []).append(action)

    out: list[AdjustedBar] = []
    for bar in bars:
        session = _session_date(bar.timestamp)
        c = _cumulative_factor(session, actions, policy)
        if c <= 0:
            raise ValueError(f"invalid cumulative adjustment factor {c} on {session}")

        # Dividends excluded from OHLC by default.
        adj_open = bar.open / c
        adj_high = bar.high / c
        adj_low = bar.low / c
        adj_close = bar.close / c

        divs = tuple(dividends_by_date.get(session, ()))
        out.append(
            AdjustedBar(
                raw=bar,
                adj_open=adj_open,
                adj_high=adj_high,
                adj_low=adj_low,
                adj_close=adj_close,
                adjustment_factor=c,
                dividends=divs,
            )
        )
    return out
