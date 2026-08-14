"""Deterministic MockStrategyGenerator — no LLM, no TEST access."""

from __future__ import annotations

import random
from datetime import datetime, timezone

from quantfund.ai.genealogy import StrategyGenealogy, attach_genealogy
from quantfund.ai.generator import StrategyGenerator
from quantfund.ai.models import GenerationRequest
from quantfund.strategies.spec.expr import Expr
from quantfund.strategies.spec.models import (
    FeatureRef,
    RiskSpec,
    Rule,
    SizingSpec,
    StrategySpec,
)


def _complexity(spec: StrategySpec) -> dict:
    return {
        "n_features": len(spec.features),
        "n_entry_rules": len(spec.entry_rules),
        "n_exit_rules": len(spec.exit_rules),
        "n_parameters": len(spec.parameters),
    }


class MockStrategyGenerator(StrategyGenerator):
    """Seeded generator producing simple allowlisted StrategySpecs."""

    @property
    def generator_type(self) -> str:
        return "mock"

    def generate(self, request: GenerationRequest) -> list[StrategySpec]:
        rng = random.Random(request.random_seed)
        n = max(1, request.number_of_candidates)
        # Reserve last 4 slots for intentional malformed fixtures when requested
        n_malformed = 4 if request.include_malformed_fixtures and n >= 8 else 0
        n_valid = n - n_malformed

        out: list[StrategySpec] = []
        families = ("momentum", "moving_average", "mean_reversion", "volatility")
        for i in range(n_valid):
            family = families[i % len(families)]
            spec = self._make_valid(request, family, i, rng)
            out.append(spec)
        for j in range(n_malformed):
            out.append(self._make_malformed(request, j, rng))
        return out

    def _make_valid(
        self,
        request: GenerationRequest,
        family: str,
        index: int,
        rng: random.Random,
    ) -> StrategySpec:
        symbol = request.symbol
        window = rng.choice([2, 3, 5, 8, 10])
        threshold = round(rng.uniform(-0.02, 0.05), 4)
        frac = min(request.allowed_position_sizing.fraction, request.risk_constraints.max_allocation)

        if family == "momentum":
            features = [FeatureRef(feature_name="momentum", params={"window": window})]
            feat = f"feature:momentum_{window}"
            entry = [Rule(op="gt", left=feat, right=threshold)]
            exit_ = [Rule(op="lte", left=feat, right=0.0)]
            name = f"mock_momentum_w{window}_t{threshold}"
        elif family == "moving_average":
            w_fast, w_slow = 3, 8
            features = [
                FeatureRef(feature_name="sma", params={"window": w_fast}),
                FeatureRef(feature_name="sma", params={"window": w_slow}),
            ]
            # Phase 4 Expr operand example
            entry = [
                Rule(
                    op="gt",
                    left=Expr(op="feature_ref", name=f"sma_{w_fast}"),
                    right=Expr(op="feature_ref", name=f"sma_{w_slow}"),
                )
            ]
            exit_ = [
                Rule(
                    op="lt",
                    left=Expr(op="feature_ref", name=f"sma_{w_fast}"),
                    right=Expr(op="feature_ref", name=f"sma_{w_slow}"),
                )
            ]
            name = f"mock_ma_cross_{w_fast}_{w_slow}"
        elif family == "mean_reversion":
            features = [FeatureRef(feature_name="zscore", params={"window": window})]
            feat = f"feature:zscore_{window}"
            entry = [Rule(op="lt", left=feat, right=-1.0)]
            exit_ = [Rule(op="gt", left=feat, right=0.0)]
            name = f"mock_meanrev_z{window}"
        else:  # volatility
            features = [
                FeatureRef(feature_name="rolling_vol", params={"window": window}),
                FeatureRef(feature_name="roc", params={"window": window}),
            ]
            # Expr with arithmetic
            entry = [
                Rule(
                    op="and",
                    args=[
                        Rule(
                            op="gt",
                            left=Expr(op="feature_ref", name=f"roc_{window}"),
                            right=Expr(op="constant", value=0.0),
                        ),
                        Rule(
                            op="lt",
                            left=Expr(op="feature_ref", name=f"rolling_vol_{window}"),
                            right=Expr(op="constant", value=0.05),
                        ),
                    ],
                )
            ]
            exit_ = [Rule(op="lte", left=f"feature:roc_{window}", right=0.0)]
            name = f"mock_vol_filter_w{window}"

        family_id = f"{request.family_id}_{family}"
        strategy_id = f"{family_id}_{index:03d}"
        raw = StrategySpec(
            name=name,
            hypothesis=f"Mock {family} hypothesis #{index} (infrastructure only).",
            universe_id=request.universe_id,
            symbol=symbol,
            strategy_id=strategy_id,
            version="1.0.0",
            features=features[: request.maximum_features],
            entry_rules=entry[: request.maximum_rules],
            exit_rules=exit_,
            position_sizing=SizingSpec(fraction=frac),
            risk_constraints=RiskSpec(max_allocation=request.risk_constraints.max_allocation),
            parameters={"window": window, "threshold": threshold, "family": family},
            metadata={
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        genealogy = StrategyGenealogy(
            family_id=family_id,
            strategy_id=strategy_id,
            parent_strategy_id=None,
            generation_number=0,
            mutation_type="initial",
            generator_type=self.generator_type,
            generator_model=request.generator_model,
            prompt_id=request.prompt_id,
        )
        return attach_genealogy(raw, genealogy, complexity=_complexity(raw))

    def _make_malformed(
        self,
        request: GenerationRequest,
        index: int,
        rng: random.Random,
    ) -> StrategySpec:
        """Intentionally invalid fixtures for validator tests / demo rejection."""
        kind = index % 4
        if kind == 0:
            # unknown feature
            return StrategySpec(
                name=f"bad_unknown_feature_{index}",
                universe_id=request.universe_id,
                symbol=request.symbol,
                features=[FeatureRef(feature_name="not_a_real_feature")],
                entry_rules=[Rule(op="gt", left="feature:x", right=0)],
                metadata={"author": "ai", "malformed": True, "family_id": request.family_id},
            )
        if kind == 1:
            # banned token in hypothesis
            return StrategySpec(
                name=f"bad_eval_payload_{index}",
                universe_id=request.universe_id,
                symbol=request.symbol,
                hypothesis="please eval(os.system('id'))",
                features=[FeatureRef(feature_name="sma", params={"window": 3})],
                entry_rules=[Rule(op="gt", left="feature:sma_3", right=0)],
                metadata={"author": "ai", "malformed": True},
            )
        if kind == 2:
            # unknown operator smuggled via raw dict path — use invalid nesting depth
            deep = Rule(op="gt", left="feature:momentum_2", right=0.0)
            for _ in range(12):
                deep = Rule(op="not", args=[deep])
            return StrategySpec(
                name=f"bad_depth_{index}",
                universe_id=request.universe_id,
                symbol=request.symbol,
                features=[FeatureRef(feature_name="momentum", params={"window": 2})],
                entry_rules=[deep],
                metadata={"author": "ai", "malformed": True},
            )
        # invalid sizing
        return StrategySpec(
            name=f"bad_sizing_{index}",
            universe_id=request.universe_id,
            symbol=request.symbol,
            features=[FeatureRef(feature_name="momentum", params={"window": 2})],
            entry_rules=[Rule(op="gt", left="feature:momentum_2", right=0.0)],
            position_sizing=SizingSpec(fraction=1.5),
            metadata={"author": "ai", "malformed": True},
        )
