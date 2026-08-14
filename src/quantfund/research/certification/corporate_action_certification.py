"""Corporate-action certification. RAW prices are never mutated here."""

from __future__ import annotations

from quantfund.data.policy import CorporateActionCoverage
from quantfund.research.certification.results import CertResult
from quantfund.research.data_contract.models import ResearchDatasetPackage

_SIMPLE = {"split", "bonus", "dividend"}


def certify_corporate_actions(package: ResearchDatasetPackage) -> CertResult:
    """Certify CA traceability and coverage. Adjustment factors are never invented.

    RAW OHLCV (``package.ohlcv``) and the CA ledger are separate collections; a
    RESEARCH-ADJUSTED series would be derived downstream without ever overwriting
    RAW, so RAW is immutable by construction.
    """
    blockers: list[str] = []
    types_seen: set[str] = set()
    for ca in package.corporate_actions:
        types_seen.add(ca.action_type)
        # Every adjustment must be fully traceable.
        if not ca.source:
            blockers.append(f"CA {ca.symbol}@{ca.ex_date}: missing source")
        if not (ca.isin or ca.symbol):
            blockers.append(f"CA @{ca.ex_date}: missing affected security")
        if ca.action_type in {"split", "bonus"} and (
            ca.ratio_num is None or ca.ratio_den in (None, 0)
        ):
            blockers.append(f"CA {ca.symbol}@{ca.ex_date}: split/bonus missing ratio")
        if ca.action_type == "dividend" and ca.cash_amount is None:
            blockers.append(f"CA {ca.symbol}@{ca.ex_date}: dividend missing cash_amount")

    if not package.corporate_actions:
        coverage = CorporateActionCoverage.NONE
        blockers.append("no corporate-action ledger (corporate_action_coverage=none)")
    elif blockers:
        coverage = CorporateActionCoverage.PARTIAL
    elif types_seen <= _SIMPLE:
        coverage = CorporateActionCoverage.SPLITS_BONUS_DIVIDENDS
    else:
        coverage = CorporateActionCoverage.FULL_VERIFIED

    return CertResult(
        dimension="corporate_actions",
        passed=coverage
        in {
            CorporateActionCoverage.SPLITS_BONUS_DIVIDENDS,
            CorporateActionCoverage.FULL_VERIFIED,
        },
        metrics={
            "corporate_action_coverage": coverage.value,
            "action_count": len(package.corporate_actions),
            "raw_series_separate": True,
        },
        blockers=[b for b in blockers if not b.startswith("no corporate-action")]
        if coverage != CorporateActionCoverage.NONE
        else blockers,
    )
