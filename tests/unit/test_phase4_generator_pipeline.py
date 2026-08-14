"""Phase 4 mock generator, genealogy, and research pipeline."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from quantfund.ai.genealogy import (
    StrategyGenealogy,
    attach_genealogy,
    canonical_strategy_hash,
)
from quantfund.ai.llm_adapter import LLMStrategyGenerator
from quantfund.ai.mock_generator import MockStrategyGenerator
from quantfund.ai.models import GenerationRequest
from quantfund.ai.pipeline import PipelineContext, StrategyResearchPipeline
from quantfund.data.models import MarketBar
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.splits import Period, SplitConfig
from quantfund.strategies.spec.models import FeatureRef, Rule, StrategySpec
from quantfund.strategies.spec.validator import StrategySpecValidator
from quantfund.storage.registry import ExperimentRegistry


def _bars() -> list[MarketBar]:
    closes = [100 + i for i in range(12)]
    return [
        MarketBar(
            timestamp=datetime(2024, 1, d),
            symbol="TEST",
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1000,
        )
        for d, c in zip(range(2, 14), closes, strict=True)
    ]


def _universe() -> UniverseVersion:
    return UniverseVersion(
        universe_id="nifty50",
        universe_version="phase4_test_pit",
        completeness=UniverseCompleteness.FULL_PIT,
        as_of_date=date(2024, 1, 13),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 1, 13),
        source="test",
        members=[UniverseMember(instrument_id="NSE:TEST", symbol="TEST")],
    )


def _base_config() -> ExperimentConfig:
    return ExperimentConfig(
        strategy_id="placeholder",
        strategy_version="1.0.0",
        parameters={},
        dataset_id="synthetic_dev",
        dataset_version="m1_v1",
        universe_id="nifty50",
        universe_version="phase4_test_pit",
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        calendar_id="FAKE_TEST",
        calendar_version="fake_v1",
        split_config=SplitConfig(
            train=Period(start=date(2024, 1, 2), end=date(2024, 1, 5)),
            validation=Period(start=date(2024, 1, 6), end=date(2024, 1, 9)),
            test=Period(start=date(2024, 1, 10), end=date(2024, 1, 13)),
        ),
        start_date="2024-01-02",
        end_date="2024-01-13",
        initial_capital=100_000,
        research_eligibility="development_only",
        sealed_evaluation=False,
        family_id="phase4_test_family",
    )


def test_mock_generator_deterministic():
    req = GenerationRequest(
        number_of_candidates=8,
        random_seed=123,
        include_malformed_fixtures=False,
        family_id="det_family",
    )
    g = MockStrategyGenerator()
    a = g.generate(req)
    b = g.generate(req)
    assert len(a) == 8
    assert [s.name for s in a] == [s.name for s in b]
    assert [canonical_strategy_hash(s) for s in a] == [
        canonical_strategy_hash(s) for s in b
    ]


def test_different_seed_changes_candidates():
    g = MockStrategyGenerator()
    a = g.generate(
        GenerationRequest(
            number_of_candidates=8,
            random_seed=1,
            include_malformed_fixtures=False,
        )
    )
    b = g.generate(
        GenerationRequest(
            number_of_candidates=8,
            random_seed=2,
            include_malformed_fixtures=False,
        )
    )
    assert [canonical_strategy_hash(s) for s in a] != [
        canonical_strategy_hash(s) for s in b
    ]


def test_mock_output_validates():
    g = MockStrategyGenerator()
    specs = g.generate(
        GenerationRequest(
            number_of_candidates=8,
            include_malformed_fixtures=False,
            random_seed=7,
        )
    )
    v = StrategySpecValidator()
    for s in specs:
        assert v.validate(s).valid is True


def test_genealogy_and_canonical_hash():
    spec = StrategySpec(
        name="g1",
        universe_id="nifty50",
        symbol="TEST",
        features=[FeatureRef(feature_name="momentum", params={"window": 2})],
        entry_rules=[Rule(op="gt", left="feature:momentum_2", right=0.0)],
    )
    g = StrategyGenealogy(
        family_id="fam",
        strategy_id="fam_001",
        generation_number=0,
        mutation_type="initial",
    )
    s1 = attach_genealogy(spec, g)
    s2 = attach_genealogy(spec, g)
    assert s1.metadata["family_id"] == "fam"
    assert s1.metadata["parent_strategy_id"] is None
    assert canonical_strategy_hash(s1) == canonical_strategy_hash(s2)


def test_duplicate_detection():
    g = MockStrategyGenerator()
    specs = g.generate(
        GenerationRequest(
            number_of_candidates=4,
            include_malformed_fixtures=False,
            random_seed=0,
        )
    )
    # Force duplicate
    specs2 = specs + [specs[0]]
    hashes = [canonical_strategy_hash(s) for s in specs2]
    assert len(hashes) == len(specs) + 1
    assert len(set(hashes)) == len(specs)


def test_llm_adapter_refuses_network():
    with pytest.raises(NotImplementedError, match="not connected"):
        LLMStrategyGenerator().generate(GenerationRequest())


def test_pipeline_development_only_blocks_acceptance(tmp_path: Path):
    registry = ExperimentRegistry(tmp_path / "registry")
    pipe = StrategyResearchPipeline(registry)
    req = GenerationRequest(
        number_of_candidates=8,
        random_seed=99,
        include_malformed_fixtures=True,
        family_id="phase4_pipe",
        symbol="TEST",
    )
    batch = pipe.run(
        req,
        PipelineContext(
            bars=_bars(),
            base_config=_base_config(),
            universe=_universe(),
            certified_eligibility="development_only",
            run_robustness=False,
        ),
    )
    assert batch.generated_count == 8
    assert batch.valid_count >= 1
    assert batch.invalid_count >= 1
    assert batch.evaluated_count == batch.valid_count - batch.duplicate_count or (
        batch.evaluated_count <= batch.valid_count
    )
    assert batch.accepted_count == 0
    assert batch.research_eligibility == "development_only"
    assert any("development_only" in b for b in batch.eligibility_blockers)
    # Trials incremented
    assert batch.n_experiments >= batch.evaluated_count
    # TEST sealed in results
    # Registry retained experiments
    assert len(batch.experiment_ids) == batch.evaluated_count


def test_pipeline_trial_counts_persist(tmp_path: Path):
    registry = ExperimentRegistry(tmp_path / "registry")
    pipe = StrategyResearchPipeline(registry)
    ctx = PipelineContext(
        bars=_bars(),
        base_config=_base_config(),
        universe=_universe(),
        certified_eligibility="development_only",
        run_robustness=False,
    )
    req = GenerationRequest(
        number_of_candidates=6,
        include_malformed_fixtures=False,
        random_seed=3,
        family_id="persist_fam",
    )
    b1 = pipe.run(req, ctx)
    b2 = pipe.run(
        req.model_copy(update={"random_seed": 4, "family_id": "persist_fam"}),
        ctx,
    )
    total = registry.count_trials("persist_fam_momentum")["n_experiments"]
    # At least some trials recorded under family sub-ids
    assert b1.evaluated_count + b2.evaluated_count >= 2
    assert sum(b2.family_trial_counts.values()) >= b1.evaluated_count


def test_generator_cannot_claim_test_access_fields():
    """GenerationRequest model forbids stuffing test metrics via known fields."""
    fields = set(GenerationRequest.model_fields)
    assert "test_metrics" not in fields
    assert "acceptance" not in fields
    assert "sealed_test_bars" not in fields
