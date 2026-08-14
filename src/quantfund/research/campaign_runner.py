"""CampaignRunner — orchestrates the research funnel above ResearchRunner."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantfund.ai.generator import StrategyGenerator
from quantfund.ai.mock_generator import MockStrategyGenerator
from quantfund.ai.models import GenerationRequest
from quantfund.data.models import MarketBar
from quantfund.data.universe.models import UniverseVersion
from quantfund.research.acceptance import CampaignAcceptancePolicy
from quantfund.research.campaign import CampaignPurpose, ResearchCampaignConfig
from quantfund.research.campaign_report import (
    build_campaign_report_payload,
    write_campaign_report,
)
from quantfund.research.campaign_state import (
    CampaignState,
    CandidateState,
    IllegalStateTransition,
    transition_campaign,
    transition_candidate,
)
from quantfund.research.candidate_pool import CandidatePool, CandidateRecord
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.runner import ResearchRunner
from quantfund.research.screening import screen_on_train
from quantfund.research.search_space import BudgetExceededError, CampaignBudgets
from quantfund.research.test_seal import (
    CampaignTestSeal,
    SealViolationError,
    assert_test_inaccessible,
)
from quantfund.research.splits import ChronologicalSplit
from quantfund.strategies.spec.interpret import interpret_strategy_spec
from quantfund.storage.registry import ExperimentRegistry


@dataclass
class CampaignRunResult:
    campaign_id: str
    config_hash: str
    final_state: str
    report: dict[str, Any]
    report_path: Path | None
    accepted_count: int
    claims: str
    warnings: list[str] = field(default_factory=list)


class CampaignRunner:
    """Freeze config → generate → screen → evaluate → seal → one-shot TEST → accept."""

    def __init__(
        self,
        registry: ExperimentRegistry,
        *,
        generator: StrategyGenerator | None = None,
        artifacts_root: Path | None = None,
    ) -> None:
        self.registry = registry
        self.generator = generator or MockStrategyGenerator()
        self.runner = ResearchRunner(registry)
        self.artifacts_root = Path(artifacts_root or registry.root / "campaigns")

    def run(
        self,
        config: ResearchCampaignConfig,
        *,
        bars: list[MarketBar],
        universe: UniverseVersion | None = None,
        resume: bool = False,
    ) -> CampaignRunResult:
        config.assert_score_policy_v1()
        config_hash = config.compute_hash()
        warnings: list[str] = []

        existing = self.registry.get_campaign(config.campaign_id)
        if existing and not resume:
            raise FileExistsError(
                f"Campaign {config.campaign_id} exists; pass resume=True to continue"
            )
        if existing and resume:
            if existing["config_hash"] != config_hash:
                raise ValueError(
                    "Cannot resume: config hash mismatch "
                    f"(stored={existing['config_hash']}, now={config_hash})"
                )
            state = CampaignState(existing["state"])
            if state == CampaignState.FINALIZED:
                report_path = self.artifacts_root / config.campaign_id
                payload = json.loads(
                    (report_path / "campaign_report.json").read_text(encoding="utf-8")
                )
                return CampaignRunResult(
                    campaign_id=config.campaign_id,
                    config_hash=config_hash,
                    final_state=state.value,
                    report=payload,
                    report_path=report_path,
                    accepted_count=int(payload["acceptance"]["accepted_count"]),
                    claims=payload["claims"],
                )
        else:
            self.registry.create_campaign(
                campaign_id=config.campaign_id,
                config_hash=config_hash,
                purpose=config.purpose.value,
                state=CampaignState.DRAFT.value,
                config_json=config.model_dump(mode="json"),
                created_at=config.created_at,
            )
            state = CampaignState.DRAFT

        budgets = CampaignBudgets(
            max_candidates=config.candidate_budget,
            max_experiments=config.experiment_budget,
        )
        # Restore consumed budgets from prior events on resume
        if resume and existing:
            trials = self.registry.count_campaign_trials(config.campaign_id)
            budgets.restore(
                candidates_consumed=trials["n_candidates"],
                experiments_consumed=trials["n_experiments"],
            )

        pool = CandidatePool(campaign_id=config.campaign_id, budgets=budgets)
        seal = CampaignTestSeal(
            campaign_id=config.campaign_id,
            config_hash=config_hash,
            selection_criterion=config.selection_criterion,
            score_policy_version=config.score_policy_version,
            dataset_id=config.dataset_id,
            dataset_version=config.dataset_version,
            acceptance_policy_id=config.acceptance_policy.policy_id,
        )
        acceptor = CampaignAcceptancePolicy(config.acceptance_policy)

        try:
            state = self._set_state(config.campaign_id, state, CampaignState.READY)
            state = self._set_state(config.campaign_id, state, CampaignState.RUNNING)

            # Prove TEST inaccessible before seal
            split = ChronologicalSplit.from_bars(bars, config.split_config)
            assert_test_inaccessible(split)

            # Generate
            if config.candidate_generator == "mock":
                req = GenerationRequest(
                    universe_id=config.universe_id,
                    symbol=config.symbol,
                    number_of_candidates=config.candidate_budget,
                    random_seed=config.random_seed,
                    include_malformed_fixtures=True,
                    family_id=config.family_id,
                    research_objective="campaign_infrastructure",
                )
                specs = self.generator.generate(req)
            elif config.candidate_generator == "human":
                raise NotImplementedError(
                    "Human Specs optional — supply via pool API in future; "
                    "demo uses mock"
                )
            else:
                raise ValueError(
                    f"Unsupported candidate_generator={config.candidate_generator}"
                )

            pool.admit_generated(
                specs,
                family_id=config.family_id,
                generator_type=getattr(self.generator, "generator_type", "mock"),
            )
            self.registry.bump_campaign_trials(
                config.campaign_id, candidates=pool.stats.generated_count
            )
            # Align budget counters with admitted unique attempts already in pool.budgets
            self.registry.append_campaign_event(
                campaign_id=config.campaign_id,
                event_type="candidates_admitted",
                payload=pool.stats.to_dict(),
            )

            # Screening (TRAIN only) for unique non-rejected
            for cand in list(pool.candidates):
                if cand.is_duplicate or cand.state == CandidateState.REJECTED:
                    continue
                if cand.spec is None:
                    continue
                strategy = interpret_strategy_spec(cand.spec)
                screen = screen_on_train(
                    strategy=strategy,
                    bars=bars,
                    split_config=config.split_config,
                    policy=config.screening_policy,
                    cost_model=config.cost_model,
                    slippage_model=config.slippage_model,
                    initial_capital=config.initial_capital,
                    dataset_id=config.dataset_id,
                    dataset_version=config.dataset_version,
                    research_eligibility=config.certified_eligibility,
                    universe_id=config.universe_id,
                    universe_version=config.universe_version,
                )
                cand.screening = screen.to_dict()
                pool.stats.screened_count += 1
                cand.state = transition_candidate(cand.state, CandidateState.SCREENED)
                self.registry.append_campaign_event(
                    campaign_id=config.campaign_id,
                    event_type="screening",
                    payload={
                        "candidate_id": cand.candidate_id,
                        "result": screen.to_dict(),
                    },
                )
                if not screen.passed:
                    cand.state = transition_candidate(
                        cand.state, CandidateState.REJECTED
                    )
                    cand.rejection_reason = f"screening:{screen.rejection_reason}"
                    pool.stats.rejected_count += 1
                else:
                    pool.stats.screen_passed_count += 1

            # Validation + robustness (+ optional WF) — no TEST
            for cand in list(pool.candidates):
                if cand.state != CandidateState.SCREENED or cand.spec is None:
                    continue
                try:
                    self._evaluate_validation(
                        config=config,
                        cand=cand,
                        bars=bars,
                        universe=universe,
                        budgets=budgets,
                        pool=pool,
                        run_walkforward=config.walkforward_enabled,
                    )
                except BudgetExceededError as exc:
                    warnings.append(str(exc))
                    self.registry.append_campaign_event(
                        campaign_id=config.campaign_id,
                        event_type="budget_exhausted",
                        payload={"stage": "validation", "error": str(exc)},
                    )
                    break

            # Seal
            state = self._set_state(config.campaign_id, state, CampaignState.SEALING)
            to_seal = [
                c
                for c in pool.candidates
                if c.state
                in {
                    CandidateState.ROBUSTNESS_EVALUATED,
                    CandidateState.WF_EVALUATED,
                }
            ]
            seal.seal(
                campaign_state=state,
                candidate_ids=[c.candidate_id for c in to_seal],
                trial_counters=self.registry.count_campaign_trials(config.campaign_id),
                selection_criterion=config.selection_criterion,
                config_hash=config_hash,
            )
            for cand in to_seal:
                cand.state = transition_candidate(cand.state, CandidateState.SEALED)
            self.registry.set_campaign_state(
                config.campaign_id, CampaignState.SEALING.value, sealed=True
            )
            self.registry.append_campaign_event(
                campaign_id=config.campaign_id,
                event_type="sealed",
                payload=seal.to_dict(),
            )

            state = self._set_state(
                config.campaign_id, CampaignState.SEALING, CampaignState.TEST_PHASE
            )

            # One-shot TEST for sealed candidates
            for cand in to_seal:
                try:
                    seal.authorize_test_evaluation(
                        candidate_id=cand.candidate_id,
                        candidate_state=cand.state,
                        prior_test_evaluations=cand.test_evaluations,
                    )
                    self._evaluate_test(
                        config=config,
                        cand=cand,
                        bars=bars,
                        universe=universe,
                        budgets=budgets,
                    )
                except (SealViolationError, BudgetExceededError) as exc:
                    warnings.append(str(exc))
                    cand.rejection_reason = f"test_seal:{exc}"
                    if cand.state != CandidateState.REJECTED:
                        try:
                            cand.state = transition_candidate(
                                cand.state, CandidateState.REJECTED
                            )
                            pool.stats.rejected_count += 1
                        except IllegalStateTransition:
                            pass

            # Acceptance
            decisions: list[dict[str, Any]] = []
            accepted_count = 0
            for cand in pool.candidates:
                if cand.state not in {
                    CandidateState.TEST_EVALUATED,
                    CandidateState.SEALED,
                    CandidateState.REJECTED,
                }:
                    if cand.state != CandidateState.REJECTED and cand.rejection_reason:
                        decisions.append(
                            {
                                "candidate_id": cand.candidate_id,
                                "accepted": False,
                                "reasons": [cand.rejection_reason],
                            }
                        )
                    continue
                if cand.state == CandidateState.REJECTED and cand.test_evaluations == 0:
                    decisions.append(
                        {
                            "candidate_id": cand.candidate_id,
                            "accepted": False,
                            "reasons": [cand.rejection_reason or "rejected_earlier"],
                        }
                    )
                    continue

                score = (cand.metrics.get("score") or {}) if cand.metrics else {}
                rob = cand.metrics.get("robustness_summary") or {}
                wf_stats = cand.metrics.get("walkforward_stats")
                decision = acceptor.decide(
                    candidate=cand,
                    purpose=config.purpose,
                    certified_eligibility=config.certified_eligibility,
                    seal=seal,
                    robustness_pass_rate=rob.get("pass_rate"),
                    robustness_fragile=bool(rob.get("fragile")),
                    walkforward_enabled=config.walkforward_enabled,
                    walkforward_stats=wf_stats,
                    score_accepted=score.get("accepted"),
                    score_rejection_reasons=score.get("rejection_reasons"),
                    trial_counts=self.registry.count_campaign_trials(
                        config.campaign_id
                    ),
                )
                acceptance_evidence_id: str | None = None
                if decision.accepted:
                    if cand.state == CandidateState.TEST_EVALUATED:
                        cand.state = transition_candidate(
                            cand.state, CandidateState.ACCEPTED
                        )
                    accepted_count += 1
                    pool.stats.accepted_count += 1
                    # Phase 10: durable StrategyAcceptanceRecord (never on
                    # development_only / exploratory — cleared below).
                    if (
                        config.certified_eligibility
                        in {"research_eligible", "production_candidate"}
                        and config.purpose != CampaignPurpose.EXPLORATORY_DEVELOPMENT
                    ):
                        try:
                            from quantfund.research.acceptance_record import (
                                build_acceptance_record_from_campaign_decision,
                                write_acceptance_record,
                            )

                            sid = (
                                cand.spec.effective_strategy_id()
                                if cand.spec is not None
                                else cand.candidate_id
                            )
                            sver = (
                                cand.spec.version
                                if cand.spec is not None
                                else "0"
                            )
                            n_trials = self.registry.count_campaign_trials(
                                config.campaign_id
                            ).get("n_experiments", 0)
                            arec = build_acceptance_record_from_campaign_decision(
                                campaign_id=config.campaign_id,
                                config_hash=config_hash,
                                dataset_id=config.dataset_id,
                                dataset_version=config.dataset_version,
                                selection_criterion=config.selection_criterion,
                                research_eligibility=config.certified_eligibility,
                                candidate_id=cand.candidate_id,
                                strategy_id=sid,
                                strategy_version=sver,
                                strategy_hash=cand.strategy_hash,
                                experiment_id=cand.test_experiment_id,
                                metrics=cand.metrics or {},
                                sealed_test_ok=bool(seal.sealed),
                                n_trials=int(n_trials),
                                acceptance_policy_version=(
                                    config.acceptance_policy.policy_id
                                ),
                            )
                            acceptance_evidence_id = arec.acceptance_evidence_id
                            write_acceptance_record(
                                self.artifacts_root
                                / config.campaign_id
                                / "acceptance"
                                / f"{arec.acceptance_evidence_id}.json",
                                arec,
                            )
                        except Exception as exc:  # noqa: BLE001 — fail closed
                            decision.accepted = False
                            decision.reasons.append(
                                f"acceptance_record_failed:{exc}"
                            )
                            accepted_count = max(0, accepted_count - 1)
                            pool.stats.accepted_count = max(
                                0, pool.stats.accepted_count - 1
                            )
                            acceptance_evidence_id = None
                else:
                    if cand.state == CandidateState.TEST_EVALUATED:
                        cand.state = transition_candidate(
                            cand.state, CandidateState.REJECTED
                        )
                        pool.stats.rejected_count += 1
                    cand.rejection_reason = ",".join(decision.reasons)
                decisions.append(
                    {
                        "candidate_id": cand.candidate_id,
                        **decision.to_dict(),
                        "acceptance_evidence_id": acceptance_evidence_id,
                    }
                )
                self.registry.append_campaign_event(
                    campaign_id=config.campaign_id,
                    event_type="acceptance_decision",
                    payload={
                        "candidate_id": cand.candidate_id,
                        **decision.to_dict(),
                        "acceptance_evidence_id": acceptance_evidence_id,
                    },
                )

            # Hard safety: development_only / exploratory → accepted=0
            if (
                config.certified_eligibility == "development_only"
                or config.purpose == CampaignPurpose.EXPLORATORY_DEVELOPMENT
            ):
                accepted_count = 0
                pool.stats.accepted_count = 0

            state = self._set_state(
                config.campaign_id, state, CampaignState.FINALIZED
            )

            payload = build_campaign_report_payload(
                campaign_id=config.campaign_id,
                config_hash=config_hash,
                final_state=state.value,
                purpose=config.purpose.value,
                dataset_id=config.dataset_id,
                dataset_version=config.dataset_version,
                certified_eligibility=config.certified_eligibility,
                source_grade=config.source_grade,
                calendar_verified=True,
                universe_completeness=(
                    universe.completeness.value if universe else "unknown"
                ),
                pool_stats=pool.stats.to_dict(),
                trial_counts=self.registry.count_campaign_trials(config.campaign_id),
                budgets=budgets.snapshot(),
                screening_policy_id=config.screening_policy.policy_id,
                walkforward_enabled=config.walkforward_enabled,
                walkforward_stats=None,
                seal=seal.to_dict(),
                acceptance_summary={"accepted_count": accepted_count, "decisions": len(decisions)},
                score_policy_version=config.score_policy_version,
                cost_model=config.cost_model,
                slippage_model=config.slippage_model,
                selection_criterion=config.selection_criterion,
                warnings=warnings,
                candidate_decisions=decisions,
                dsr_notes={
                    "n_trials": self.registry.count_campaign_trials(
                        config.campaign_id
                    ).get("n_experiments", 0),
                    "selection_criterion": config.selection_criterion,
                },
            )
            report_path = write_campaign_report(
                self.artifacts_root / config.campaign_id, payload
            )
            # Persist pool snapshot
            (report_path / "candidate_pool.json").write_text(
                json.dumps(pool.to_serializable(), indent=2, default=str),
                encoding="utf-8",
            )
            self.registry.append_campaign_event(
                campaign_id=config.campaign_id,
                event_type="finalized",
                payload={
                    "accepted_count": accepted_count,
                    "claims": payload["claims"],
                },
            )
            return CampaignRunResult(
                campaign_id=config.campaign_id,
                config_hash=config_hash,
                final_state=state.value,
                report=payload,
                report_path=report_path,
                accepted_count=accepted_count,
                claims=payload["claims"],
                warnings=warnings,
            )
        except Exception as exc:
            try:
                if state not in {CampaignState.FINALIZED, CampaignState.FAILED}:
                    self.registry.set_campaign_state(
                        config.campaign_id, CampaignState.FAILED.value
                    )
            except Exception:
                pass
            self.registry.append_campaign_event(
                campaign_id=config.campaign_id,
                event_type="failed",
                payload={"error": str(exc)},
            )
            raise

    def _set_state(
        self,
        campaign_id: str,
        current: CampaignState,
        target: CampaignState,
    ) -> CampaignState:
        new = transition_campaign(current, target)
        self.registry.set_campaign_state(campaign_id, new.value)
        return new

    def _base_experiment_config(
        self,
        config: ResearchCampaignConfig,
        cand: CandidateRecord,
        *,
        sealed_evaluation: bool,
        purpose: str,
    ) -> ExperimentConfig:
        assert cand.spec is not None
        return ExperimentConfig(
            strategy_id=cand.spec.strategy_id,
            strategy_version=cand.spec.version,
            parameters=dict(cand.spec.parameters),
            dataset_id=config.dataset_id,
            dataset_version=config.dataset_version,
            universe_id=config.universe_id,
            universe_version=config.universe_version,
            feature_versions=dict(config.feature_versions),
            feature_requests=list(config.feature_requests),
            cost_model=config.cost_model,
            slippage_model=config.slippage_model,
            calendar_id=config.calendar_id,
            calendar_version=config.calendar_version,
            split_config=config.split_config,
            walkforward_config=config.walkforward_config
            if config.walkforward_enabled
            else None,
            start_date=config.split_config.train.start.isoformat(),
            end_date=config.split_config.test.end.isoformat(),
            initial_capital=config.initial_capital,
            random_seed=config.random_seed,
            code_version=config.code_version,
            research_eligibility=config.certified_eligibility,
            purpose=purpose,
            selection_criterion=config.selection_criterion,
            sealed_evaluation=sealed_evaluation,
            score_policy=config.score_policy_version,
            family_id=config.family_id,
        )

    def _evaluate_validation(
        self,
        *,
        config: ResearchCampaignConfig,
        cand: CandidateRecord,
        bars: list[MarketBar],
        universe: UniverseVersion | None,
        budgets: CampaignBudgets,
        pool: CandidatePool,
        run_walkforward: bool,
    ) -> None:
        assert cand.spec is not None
        budgets.consume_experiment(label=cand.candidate_id)
        exp_cfg = self._base_experiment_config(
            config, cand, sealed_evaluation=False, purpose="candidate"
        )
        strategy_factory = lambda s=cand.spec: interpret_strategy_spec(s)
        result = self.runner.evaluate(
            strategy_factory=strategy_factory,
            bars=bars,
            config=exp_cfg,
            universe=universe,
            feature_requests=config.feature_requests,
            run_robustness=True,
            run_walkforward=run_walkforward,
            certified_eligibility=config.certified_eligibility,
        )
        self.registry.bump_campaign_trials(
            config.campaign_id, experiments=1, validation_trials=1
        )
        cand.validation_experiment_id = result.experiment_id
        cand.metrics = {
            "metrics_by_split": result.metrics_by_split,
            "score": result.score,
            "robustness_summary": result.robustness_summary,
            "deflated_sharpe": result.deflated_sharpe,
            "status": result.status,
        }
        pool.stats.evaluated_count += 1
        cand.state = transition_candidate(
            cand.state, CandidateState.VALIDATION_EVALUATED
        )
        # Always mark robustness evaluated after runner (runner runs robustness)
        cand.state = transition_candidate(
            cand.state, CandidateState.ROBUSTNESS_EVALUATED
        )
        if run_walkforward:
            wf = (result.metrics_by_split or {}).get("walkforward") or {}
            windows = wf.get("windows") or []
            sharpes = [
                w.get("metrics", {}).get("sharpe_ratio")
                for w in windows
                if w.get("metrics", {}).get("sharpe_ratio") is not None
            ]
            frac_pos = (
                sum(1 for s in sharpes if s is not None and s > 0) / len(sharpes)
                if sharpes
                else 0.0
            )
            med = statistics.median(sharpes) if sharpes else None
            cand.metrics["walkforward_stats"] = {
                "n_windows": len(windows),
                "fraction_positive_windows": frac_pos,
                "median_window_sharpe": med,
                "mean_window_sharpe": statistics.mean(sharpes) if sharpes else None,
            }
            cand.state = transition_candidate(cand.state, CandidateState.WF_EVALUATED)

        # Soft validation gate — reject if empty validation or score hard-fails structure
        val = (result.metrics_by_split or {}).get("validation") or {}
        if val.get("error") == "empty_split":
            cand.state = transition_candidate(cand.state, CandidateState.REJECTED)
            cand.rejection_reason = "empty_validation"
            pool.stats.rejected_count += 1
            return
        if result.rejection_reasons and "fragile_under_cost_stress" in result.rejection_reasons:
            if config.robustness_policy.reject_if_fragile:
                cand.state = transition_candidate(cand.state, CandidateState.REJECTED)
                cand.rejection_reason = "fragile_under_cost_stress"
                pool.stats.rejected_count += 1
                return

        self.registry.append_campaign_event(
            campaign_id=config.campaign_id,
            event_type="validation_evaluated",
            payload={
                "candidate_id": cand.candidate_id,
                "experiment_id": result.experiment_id,
                "status": result.status,
            },
        )

    def _evaluate_test(
        self,
        *,
        config: ResearchCampaignConfig,
        cand: CandidateRecord,
        bars: list[MarketBar],
        universe: UniverseVersion | None,
        budgets: CampaignBudgets,
    ) -> None:
        assert cand.spec is not None
        budgets.consume_experiment(label=f"test:{cand.candidate_id}")
        exp_cfg = self._base_experiment_config(
            config, cand, sealed_evaluation=True, purpose="sealed_test"
        )
        strategy_factory = lambda s=cand.spec: interpret_strategy_spec(s)
        result = self.runner.evaluate(
            strategy_factory=strategy_factory,
            bars=bars,
            config=exp_cfg,
            universe=universe,
            feature_requests=config.feature_requests,
            run_robustness=False,
            run_walkforward=False,
            certified_eligibility=config.certified_eligibility,
        )
        cand.test_evaluations += 1
        cand.test_experiment_id = result.experiment_id
        cand.metrics["test"] = (result.metrics_by_split or {}).get("test")
        cand.state = transition_candidate(cand.state, CandidateState.TEST_EVALUATED)
        self.registry.bump_campaign_trials(
            config.campaign_id, experiments=1, test_evaluations=1
        )
        self.registry.append_campaign_event(
            campaign_id=config.campaign_id,
            event_type="test_evaluated",
            payload={
                "candidate_id": cand.candidate_id,
                "experiment_id": result.experiment_id,
                "test_evaluations": cand.test_evaluations,
            },
        )
