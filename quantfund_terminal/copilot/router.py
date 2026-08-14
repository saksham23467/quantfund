"""Deterministic intent router for the Research Copilot."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class CopilotPlan:
    intent: str
    summary: str
    generated_sql: str
    workflow_steps: list[str]
    api_calls: list[str]
    disclaimer: str = (
        "Plan only. Runs against the SELECTED dataset and inherits its "
        "certification verdict. No orders, no paper/live trading."
    )
    safety_note: str = "read_only; broker_writes=DISABLED; kill_switch=ARMED"
    confidence: float = 0.9
    matched: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


_RULES: list[tuple[str, re.Pattern]] = [
    ("find_momentum_stocks", re.compile(r"\b(momentum|top\s+performers|winners|trending)\b", re.I)),
    ("build_low_vol_strategy", re.compile(r"\b(low[\s-]?vol|minimum\s+variance|defensive|stable)\b", re.I)),
    ("explain_sharpe_drop", re.compile(r"\b(sharpe|why.*(fell|drop|declin)|performance.*(fell|drop))\b", re.I)),
    ("run_backtest", re.compile(r"\b(backtest|simulate|test\s+strateg)\b", re.I)),
    ("check_dataset_eligibility", re.compile(r"\b(certif|eligib|provenance|dataset\s+quality)\b", re.I)),
    ("mean_reversion", re.compile(r"\b(mean[\s-]?revers|contrarian|oversold)\b", re.I)),
    ("breakout", re.compile(r"\b(breakout|52[\s-]?week\s+high|new\s+high)\b", re.I)),
]


def _plan_for(intent: str, prompt: str) -> CopilotPlan:
    if intent == "find_momentum_stocks":
        return CopilotPlan(
            intent=intent,
            summary="Rank the PIT universe by 6-month momentum and return the leaders.",
            generated_sql=(
                "SELECT fs.symbol, fs.score AS momentum_score, fs.as_of\n"
                "FROM factor_scores fs\n"
                "JOIN datasets d ON d.id = fs.dataset_id\n"
                "WHERE fs.factor = 'momentum'\n"
                "  AND fs.as_of = (SELECT max(as_of) FROM factor_scores WHERE factor='momentum')\n"
                "  AND d.certification = 'RESEARCH_ELIGIBLE'\n"
                "ORDER BY fs.score DESC\n"
                "LIMIT 20;"
            ),
            workflow_steps=[
                "Resolve PIT universe membership for as_of date (research.universe).",
                "Compute momentum factor scores (analytics_engine.factors).",
                "Filter to the certified dataset only; DEVELOPMENT_ONLY data is flagged.",
                "Return ranked leaders with provenance + certification badge.",
            ],
            api_calls=["GET /api/factors?factor=momentum", "GET /api/certification"],
        )
    if intent in {"build_low_vol_strategy", "mean_reversion", "breakout"}:
        family = {
            "build_low_vol_strategy": "volatility",
            "mean_reversion": "mean_reversion",
            "breakout": "breakout",
        }[intent]
        return CopilotPlan(
            intent=intent,
            summary=f"Draft a {family} strategy and stage it for a gated backtest.",
            generated_sql=(
                "INSERT INTO strategies (name, family, params, status, created_by)\n"
                f"VALUES ('copilot_{family}', '{family}', :params, 'DRAFT', 'copilot')\n"
                "RETURNING id;"
            ),
            workflow_steps=[
                f"Create a {family} strategy definition (Research Lab, no code).",
                "Select universe + date range + costs + slippage.",
                "Run backtest via analytics_engine (next-bar execution, explicit costs).",
                "Persist experiment with dataset_hash + experiment_hash (audit).",
                "Show verdict; acceptance requires research_eligible dataset (fail-closed).",
            ],
            api_calls=["POST /api/strategies", "POST /api/backtest", "GET /api/audit"],
        )
    if intent == "explain_sharpe_drop":
        return CopilotPlan(
            intent=intent,
            summary="Attribute a Sharpe decline to costs, turnover, regime and factor drift.",
            generated_sql=(
                "SELECT b.id, b.sharpe, b.turnover, b.cost_bps, b.slippage_bps, b.window\n"
                "FROM backtests b\n"
                "WHERE b.strategy_id = :strategy_id\n"
                "ORDER BY b.window;"
            ),
            workflow_steps=[
                "Load rolling Sharpe windows for the strategy (analytics_engine.metrics).",
                "Decompose: gross vs net (cost/slippage drag), turnover spikes.",
                "Cross-check factor exposure drift (analytics_engine.factors).",
                "Flag regime shifts (volatility) over the decline window.",
            ],
            api_calls=["GET /api/backtest/{id}", "GET /api/factors"],
        )
    if intent == "run_backtest":
        return CopilotPlan(
            intent=intent,
            summary="Run a gated backtest with explicit costs/slippage and record it.",
            generated_sql=(
                "INSERT INTO backtests (strategy_id, dataset_id, start, end, cost_bps,\n"
                "  slippage_bps, cagr, sharpe, sortino, max_dd, dataset_hash, experiment_hash)\n"
                "VALUES (:strategy_id, :dataset_id, :start, :end, :cost_bps, :slippage_bps,\n"
                "  :cagr, :sharpe, :sortino, :max_dd, :dataset_hash, :experiment_hash);"
            ),
            workflow_steps=[
                "Validate dataset certification before running (moat).",
                "Execute vectorized backtest (no look-ahead).",
                "Compute institutional metric set + report.",
                "Write immutable audit record.",
            ],
            api_calls=["POST /api/backtest", "GET /api/certification", "GET /api/audit"],
        )
    if intent == "check_dataset_eligibility":
        return CopilotPlan(
            intent=intent,
            summary="Explain the dataset's certification verdict and blockers.",
            generated_sql=(
                "SELECT d.dataset_id, c.verdict, c.source_grade, c.membership_coverage_ratio,\n"
                "  c.instrument_identity_coverage, c.delisted_coverage, c.calendar_verified\n"
                "FROM certifications c JOIN datasets d ON d.id = c.dataset_id\n"
                "ORDER BY c.generated_at DESC LIMIT 1;"
            ),
            workflow_steps=[
                "Load latest certification (research.certification).",
                "Summarize source/PIT/identity/delisting/calendar/CA coverage.",
                "Explain why RESEARCH_ELIGIBLE vs DEVELOPMENT_ONLY (fail-closed).",
            ],
            api_calls=["GET /api/certification"],
        )
    return CopilotPlan(
        intent="unrecognized",
        summary="Could not map the request to a known research workflow.",
        generated_sql="-- no query generated",
        workflow_steps=["Ask the user to refine (momentum, low-vol, backtest, certification, ...)."],
        api_calls=[],
        confidence=0.2,
        matched=False,
    )


def plan(prompt: str) -> CopilotPlan:
    text = (prompt or "").strip()
    for intent, pattern in _RULES:
        if pattern.search(text):
            return _plan_for(intent, text)
    return _plan_for("unrecognized", text)
