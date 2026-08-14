"""Machine-readable JSON and human-readable performance reports."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from quantfund.analytics.metrics import PerformanceMetrics, compute_metrics
from quantfund.backtest.engine import BacktestResult


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.4f}%"


def _fmt_num(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def build_report_dict(result: BacktestResult, metrics: PerformanceMetrics | None = None) -> dict[str, Any]:
    metrics = metrics or compute_metrics(result)
    return {
        "experiment_id": result.experiment_id,
        "strategy_id": result.strategy_id,
        "strategy_name": result.strategy_name,
        "strategy_version": result.strategy_version,
        "code_version": result.code_version,
        "parameters": result.parameters,
        "data_source": result.data_source,
        "data_version": result.data_version,
        "dataset_id": result.dataset_id,
        "dataset_version": result.dataset_version,
        "research_eligibility": result.research_eligibility,
        "source_grade": result.source_grade,
        "universe_id": result.universe_id,
        "universe_version": result.universe_version,
        "universe_completeness": result.universe_completeness,
        "adjustment_policy_id": result.adjustment_policy_id,
        "dataset_warnings": list(result.dataset_warnings),
        "start_date": result.start_date.isoformat() if result.start_date else None,
        "end_date": result.end_date.isoformat() if result.end_date else None,
        "initial_capital": result.initial_capital,
        "final_capital": result.final_equity,
        "cost_model": result.cost_model,
        "slippage_model": result.slippage_model,
        "metrics": {
            "total_return": metrics.total_return,
            "cagr": metrics.cagr,
            "annualized_volatility": metrics.annualized_volatility,
            "sharpe_ratio": metrics.sharpe_ratio,
            "sortino_ratio": metrics.sortino_ratio,
            "maximum_drawdown": metrics.maximum_drawdown,
            "calmar_ratio": metrics.calmar_ratio,
            "win_rate": metrics.win_rate,
            "average_win": metrics.average_win,
            "average_loss": metrics.average_loss,
            "profit_factor": metrics.profit_factor,
            "number_of_trades": metrics.number_of_trades,
            "turnover": metrics.turnover,
            "total_transaction_costs": metrics.total_transaction_costs,
            "total_slippage": metrics.total_slippage,
            "notes": list(metrics.notes),
        },
        "realized_pnl": result.portfolio.realized_pnl,
        "unrealized_pnl": result.portfolio.unrealized_pnl(),
        "cash": result.portfolio.cash,
        "fills": len(result.portfolio.fills),
        "rejected_orders": len(result.rejected_orders),
    }


def render_text_report(report: dict[str, Any]) -> str:
    m = report["metrics"]
    lines = [
        "QuantFund Backtest Report (Research Only — Not Live Trading)",
        "=" * 60,
    ]
    if report.get("dataset_warnings"):
        lines.append("*** DATASET WARNINGS (READ BEFORE INTERPRETING RESULTS) ***")
        for w in report["dataset_warnings"]:
            lines.append(f"  ! {w}")
        lines.append("=" * 60)
    if report.get("research_eligibility"):
        lines.append(f"Research Eligibility: {report['research_eligibility']}")
        if report["research_eligibility"] == "development_only":
            lines.append(
                "This run is NOT final strategy validation. "
                "Results are hypotheses for infrastructure/exploration only."
            )
    lines.extend(
        [
            f"Experiment ID     : {report['experiment_id']}",
            f"Strategy ID       : {report['strategy_id']}",
            f"Strategy Version  : {report['strategy_version']}",
            f"Data Source       : {report['data_source']} ({report['data_version']})",
            f"Dataset           : {report.get('dataset_id')} @ {report.get('dataset_version')}",
            f"Period            : {report['start_date']} → {report['end_date']}",
            f"Cost Model        : {report['cost_model']}",
            f"Slippage Model    : {report['slippage_model']}",
            "-" * 60,
            f"Initial Capital   : {report['initial_capital']:.2f}",
            f"Final Capital     : {report['final_capital']:.2f}",
            f"Total Return      : {_fmt_pct(m['total_return'])}",
            f"CAGR              : {_fmt_pct(m['cagr'])}",
            f"Sharpe            : {_fmt_num(m['sharpe_ratio'])}",
            f"Sortino           : {_fmt_num(m['sortino_ratio'])}",
            f"Max Drawdown      : {_fmt_pct(m['maximum_drawdown'])}",
            f"Number of Trades  : {m['number_of_trades']}",
            f"Transaction Costs : {m['total_transaction_costs']:.4f}",
            f"Total Slippage    : {m['total_slippage']:.4f}",
            "-" * 60,
            f"Notes: {', '.join(m['notes']) if m['notes'] else 'none'}",
            "",
            "Disclaimer: Backtest results are hypotheses, not guarantees.",
        ]
    )
    return "\n".join(lines)


def write_reports(result: BacktestResult, output_dir: Path) -> tuple[Path, Path]:
    """Write JSON and text reports; return (json_path, text_path)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = compute_metrics(result)
    report = build_report_dict(result, metrics)

    json_path = output_dir / f"{result.experiment_id}_report.json"
    text_path = output_dir / f"{result.experiment_id}_report.txt"

    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    text_path.write_text(render_text_report(report), encoding="utf-8")

    # Also persist equity curve for reproducibility
    equity_path = output_dir / f"{result.experiment_id}_equity.json"
    equity_path.write_text(
        json.dumps(
            [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "equity": p.equity,
                    "cash": p.cash,
                    "market_value": p.market_value,
                    "realized_pnl": p.realized_pnl,
                    "unrealized_pnl": p.unrealized_pnl,
                }
                for p in result.portfolio.equity_curve
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    # Persist event log
    events_path = output_dir / f"{result.experiment_id}_events.json"
    events_path.write_text(json.dumps(result.events, indent=2), encoding="utf-8")

    # Metadata bundle
    meta_path = output_dir / f"{result.experiment_id}_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "experiment_id": result.experiment_id,
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                "data_source": result.data_source,
                "data_version": result.data_version,
                "start_date": report["start_date"],
                "end_date": report["end_date"],
                "initial_capital": result.initial_capital,
                "cost_model": result.cost_model,
                "slippage_model": result.slippage_model,
                "parameters": result.parameters,
                "code_version": result.code_version,
                "dataset_id": result.dataset_id,
                "dataset_version": result.dataset_version,
                "research_eligibility": result.research_eligibility,
                "source_grade": result.source_grade,
                "universe_id": result.universe_id,
                "universe_version": result.universe_version,
                "universe_completeness": result.universe_completeness,
                "adjustment_policy_id": result.adjustment_policy_id,
                "dataset_warnings": list(result.dataset_warnings),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return json_path, text_path
