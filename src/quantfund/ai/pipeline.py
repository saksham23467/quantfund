"""StrategyResearchPipeline — generator → validator → interpreter → ResearchRunner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from quantfund.ai.genealogy import canonical_strategy_hash
from quantfund.ai.generator import StrategyGenerator
from quantfund.ai.models import GenerationRequest, PipelineBatchResult
from quantfund.ai.mock_generator import MockStrategyGenerator
from quantfund.data.models import MarketBar
from quantfund.data.universe.models import UniverseVersion
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.runner import ResearchRunner
from quantfund.strategies.spec.interpret import interpret_strategy_spec
from quantfund.strategies.spec.models import StrategySpec
from quantfund.strategies.spec.validator import StrategySpecValidator
from quantfund.storage.registry import ExperimentRegistry


@dataclass
class PipelineContext:
    """Trusted evaluation context supplied by the caller — never by the generator."""

    bars: list[MarketBar]
    base_config: ExperimentConfig
    universe: UniverseVersion | None = None
    certified_eligibility: str | None = None
    run_robustness: bool = False
    run_walkforward: bool = False


class StrategyResearchPipeline:
    """Orchestrates AI candidates through the existing research spine.

    Generator never receives evaluation results within a batch.
    Acceptance is decided only by ResearchRunner / scoring.
    """

    def __init__(
        self,
        registry: ExperimentRegistry,
        *,
        generator: StrategyGenerator | None = None,
        validator: StrategySpecValidator | None = None,
    ) -> None:
        self.registry = registry
        self.generator = generator or MockStrategyGenerator()
        self.validator = validator or StrategySpecValidator()
        self.runner = ResearchRunner(registry)

    def run(
        self,
        request: GenerationRequest,
        context: PipelineContext,
    ) -> PipelineBatchResult:
        # 1) Generate (untrusted)
        candidates = self.generator.generate(request)

        valid: list[StrategySpec] = []
        invalid_errors: list[dict[str, Any]] = []
        for spec in candidates:
            result = self.validator.validate(spec)
            if result.valid:
                valid.append(spec if isinstance(spec, StrategySpec) else spec)
            else:
                invalid_errors.append(
                    {
                        "name": getattr(spec, "name", "?"),
                        "errors": result.to_dict()["errors"],
                    }
                )

        # Ensure valid list items are StrategySpec
        valid_specs: list[StrategySpec] = []
        for spec in valid:
            if isinstance(spec, dict):
                valid_specs.append(StrategySpec.model_validate(spec))
            else:
                valid_specs.append(spec)

        # 2) Deduplicate by canonical hash
        seen: set[str] = set()
        unique: list[StrategySpec] = []
        duplicate_count = 0
        for spec in valid_specs:
            h = canonical_strategy_hash(spec)
            if h in seen:
                duplicate_count += 1
                continue
            seen.add(h)
            # Skip if already evaluated in registry
            # (config hash differs; we still track strategy-level duplicates in-batch)
            unique.append(spec)

        # 3) Evaluate each unique valid candidate via existing ResearchRunner
        experiment_ids: list[str] = []
        rejected = 0
        accepted = 0
        evaluated = 0
        notes: list[str] = [
            "Generator did not receive TEST metrics or acceptance decisions.",
            "Arbitrary code execution denied by validator/interpreter allowlists.",
            "Live trading disabled. Brokers: none.",
        ]

        eligibility = context.base_config.research_eligibility
        blockers = []
        if eligibility == "development_only":
            blockers.append("development_only_dataset_cannot_be_accepted")
            notes.append("DEVELOPMENT_ONLY — no candidate may be accepted_for_validation_pipeline.")

        for spec in unique:
            feature_requests: list[dict[str, Any]] = []
            for fr in spec.features:
                req: dict[str, Any] = {"name": fr.feature_name}
                if "window" in fr.params:
                    req["window"] = fr.params["window"]
                feature_requests.append(req)
            cfg = context.base_config.model_copy(
                update={
                    "experiment_id": uuid4().hex,
                    "strategy_id": spec.effective_strategy_id(),
                    "strategy_version": spec.version,
                    "parameters": dict(spec.parameters),
                    "feature_requests": feature_requests,
                    "family_id": str(
                        spec.metadata.get("family_id") or request.family_id
                    ),
                    "purpose": "candidate",
                    "sealed_evaluation": False,
                }
            )

            def factory(s: StrategySpec = spec) -> Any:
                return interpret_strategy_spec(s)

            result = self.runner.evaluate(
                strategy_factory=factory,
                bars=context.bars,
                config=cfg,
                universe=context.universe,
                feature_requests=feature_requests,
                run_robustness=context.run_robustness,
                run_walkforward=context.run_walkforward,
                certified_eligibility=context.certified_eligibility or eligibility,
            )
            evaluated += 1
            experiment_ids.append(result.experiment_id)
            score = result.score or {}
            if score.get("accepted"):
                accepted += 1
            else:
                rejected += 1

        # Family trial totals from registry
        family_ids = {request.family_id}
        for spec in unique:
            fid = spec.metadata.get("family_id")
            if fid:
                family_ids.add(str(fid))
        family_trials = {
            fid: self.registry.count_trials(fid)["n_experiments"] for fid in sorted(family_ids)
        }
        n_experiments = sum(family_trials.values())

        return PipelineBatchResult(
            generated_count=len(candidates),
            valid_count=len(valid_specs),
            invalid_count=len(invalid_errors),
            duplicate_count=duplicate_count,
            evaluated_count=evaluated,
            rejected_count=rejected,
            accepted_count=accepted,
            n_experiments=n_experiments,
            family_trial_counts=family_trials,
            research_eligibility=eligibility,
            eligibility_blockers=blockers,
            invalid_errors=invalid_errors,
            specs=unique,
            experiment_ids=experiment_ids,
            notes=notes,
        )
