"""API request/response contracts (Pydantic). Response bodies documented in
docs/API_CONTRACTS.md."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    family: str = Field("momentum", description="momentum|trend|mean_reversion|breakout|volatility")
    universe: str = "DEMO_NIFTY20"
    start: str | None = None
    end: str | None = None
    lookback: int = 126
    holding_top_n: int = 5
    rebalance_days: int = 21
    cost_bps: float = 10.0
    slippage_bps: float = 5.0


class StrategyCreateRequest(BaseModel):
    name: str
    family: str = "momentum"
    params: dict = Field(default_factory=dict)


class Holding(BaseModel):
    symbol: str
    weight: float | None = None
    quantity: float | None = None
    price: float | None = None


class PortfolioRequest(BaseModel):
    holdings: list[Holding]


class RiskRequest(BaseModel):
    holdings: list[Holding]


class CopilotRequest(BaseModel):
    prompt: str


class FactorQuery(BaseModel):
    lookback: int = 126


# --- v2 SaaS schemas --------------------------------------------------------
class StudioRequest(BaseModel):
    holdings: list[Holding]
    lookback: int = 126


class ScenarioRequest(BaseModel):
    holdings: list[Holding]
    custom: dict[str, dict[str, float]] | None = None
    lookback: int = 126


class PublishRequest(BaseModel):
    name: str
    family: str = "momentum"
    params: dict = Field(default_factory=dict)
    cost_bps: float = 10.0
    slippage_bps: float = 5.0


class CheckoutRequest(BaseModel):
    plan: str = "team"


class OrgCreateRequest(BaseModel):
    name: str
    slug: str
    plan: str = "trial"
