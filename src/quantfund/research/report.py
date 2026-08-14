"""Research report generation (JSON + text)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.research.experiment import ExperimentConfig, ExperimentResult


def build_research_report(
    config: ExperimentConfig,
    result: ExperimentResult,
    trial_accounting: dict[str, Any],
) -> dict[str, Any]:
    oos = result.metrics_by_split.get("validation") or result.metrics_by_split.get("full") or {}
    return {
        "strategy": {
            "strategy_id": config.strategy_id,
            "strategy_version": config.strategy_version,
            "parameters": config.parameters,
        },
        "dataset": {
            "dataset_id": config.dataset_id,
            "dataset_version": config.dataset_version,
            "research_eligibility": config.research_eligibility,
        },
        "universe": {
            "universe_id": config.universe_id,
            "universe_version": config.universe_version,
        },
        "features": config.feature_versions,
        "feature_requests": config.feature_requests,
        "calendar": {
            "calendar_id": config.calendar_id,
            "calendar_version": config.calendar_version,
        },
        "costs": {
            "cost_model": config.cost_model,
            "slippage_model": config.slippage_model,
        },
        "splits": config.split_config.model_dump(mode="json") if config.split_config else None,
        "walkforward": (
            config.walkforward_config.model_dump(mode="json")
            if config.walkforward_config
            else None
        ),
        "period": {"start": config.start_date, "end": config.end_date},
        "initial_capital": config.initial_capital,
        "code_version": config.code_version,
        "performance_oos": oos,
        "metrics_by_split": result.metrics_by_split,
        "score": result.score,
        "deflated_sharpe": result.deflated_sharpe,
        "robustness": result.robustness_summary,
        "research_integrity": {
            "status": result.status,
            "rejection_reasons": result.rejection_reasons,
            "warnings": result.warnings,
            "trial_accounting": trial_accounting,
            "config_hash": result.config_hash,
            "sealed_evaluation": config.sealed_evaluation,
            "selection_criterion": config.selection_criterion,
        },
    }


def render_research_text(report: dict[str, Any]) -> str:
    ri = report["research_integrity"]
    lines = [
        "QuantFund Research Report",
        "=" * 60,
        f"Status              : {ri['status']}",
        f"Strategy            : {report['strategy']['strategy_id']} "
        f"v{report['strategy']['strategy_version']}",
        f"Dataset             : {report['dataset']['dataset_id']} @ "
        f"{report['dataset']['dataset_version']}",
        f"Eligibility         : {report['dataset']['research_eligibility']}",
        f"Config hash         : {ri['config_hash']}",
        f"Trials in family    : {ri['trial_accounting'].get('n_experiments')}",
        f"Deflated Sharpe     : {report.get('deflated_sharpe')}",
        "-" * 60,
    ]
    if ri["warnings"]:
        lines.append("WARNINGS:")
        for w in ri["warnings"]:
            lines.append(f"  ! {w}")
    if ri["rejection_reasons"]:
        lines.append("REJECTION REASONS:")
        for r in ri["rejection_reasons"]:
            lines.append(f"  - {r}")
    oos = report.get("performance_oos") or {}
    lines.extend(
        [
            "-" * 60,
            f"OOS total return    : {oos.get('total_return')}",
            f"OOS Sharpe          : {oos.get('sharpe_ratio')}",
            f"OOS Max DD          : {oos.get('maximum_drawdown')}",
            f"OOS trades          : {oos.get('number_of_trades')}",
            f"OOS costs           : {oos.get('total_transaction_costs')}",
            f"Score total         : {(report.get('score') or {}).get('total')}",
            f"Score accepted      : {(report.get('score') or {}).get('accepted')}",
            "",
            "Backtest results are hypotheses, not guarantees.",
        ]
    )
    return "\n".join(lines)


def write_research_report(
    output_dir: Path,
    *,
    config: ExperimentConfig,
    result: ExperimentResult,
    trial_accounting: dict[str, Any],
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_research_report(config, result, trial_accounting)
    json_path = output_dir / "research_report.json"
    text_path = output_dir / "research_report.txt"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    text_path.write_text(render_research_text(report), encoding="utf-8")
    return json_path, text_path
