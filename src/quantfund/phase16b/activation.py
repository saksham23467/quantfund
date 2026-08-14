"""Immutable canary ActivationRecord — human confirmation + expiry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from quantfund.paper.models import deterministic_id, state_hash
from quantfund.phase15.models import scrub_secrets


CANARY_CONFIRM_PHRASE = "I_CONFIRM_CONTROLLED_LIVE_CANARY"


@dataclass(frozen=True)
class CanaryActivationRecord:
    activation_id: str
    strategy_id: str
    strategy_version: str
    strategy_hash: str
    config_hash: str
    dataset_provenance: str
    broker: str
    account_hash: str
    capital_limit: float
    max_daily_loss: float
    max_position_value: float
    max_order_quantity: float
    max_order_value: float
    max_orders_per_day: int
    max_turnover_per_day: float
    activation_timestamp: str
    expiry_timestamp: str
    human_confirmation: str
    activation_nonce: str
    configuration_hash: str
    allowed_instruments: tuple[str, ...]
    allowed_sides: tuple[str, ...]
    allowed_order_types: tuple[str, ...]
    allowed_products: tuple[str, ...]
    actor: str
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return scrub_secrets(
            {
                "activation_id": self.activation_id,
                "strategy_id": self.strategy_id,
                "strategy_version": self.strategy_version,
                "strategy_hash": self.strategy_hash,
                "config_hash": self.config_hash,
                "dataset_provenance": self.dataset_provenance,
                "broker": self.broker,
                "account_hash": self.account_hash,
                "capital_limit": self.capital_limit,
                "max_daily_loss": self.max_daily_loss,
                "max_position_value": self.max_position_value,
                "max_order_quantity": self.max_order_quantity,
                "max_order_value": self.max_order_value,
                "max_orders_per_day": self.max_orders_per_day,
                "max_turnover_per_day": self.max_turnover_per_day,
                "activation_timestamp": self.activation_timestamp,
                "expiry_timestamp": self.expiry_timestamp,
                "human_confirmation": "***CONFIRMED***"
                if self.human_confirmation == CANARY_CONFIRM_PHRASE
                else "INVALID",
                "activation_nonce": self.activation_nonce,
                "configuration_hash": self.configuration_hash,
                "allowed_instruments": list(self.allowed_instruments),
                "allowed_sides": list(self.allowed_sides),
                "allowed_order_types": list(self.allowed_order_types),
                "allowed_products": list(self.allowed_products),
                "actor": self.actor,
                "active": self.active,
                "record_kind": "LIVE_CANARY_ACTIVATION",
            }
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        exp = datetime.fromisoformat(self.expiry_timestamp.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now >= exp

    def validate_against(
        self,
        *,
        strategy_id: str,
        strategy_hash: str,
        config_hash: str,
        now: datetime | None = None,
    ) -> list[str]:
        blockers: list[str] = []
        if not self.active:
            blockers.append("activation_inactive")
        if self.is_expired(now):
            blockers.append("activation_expired")
        if self.human_confirmation != CANARY_CONFIRM_PHRASE:
            blockers.append("invalid_confirmation")
        if strategy_id != self.strategy_id:
            blockers.append("strategy_not_allowlisted")
        if strategy_hash != self.strategy_hash:
            blockers.append("strategy_hash_mismatch")
        if config_hash != self.config_hash:
            blockers.append("config_hash_mismatch")
        return blockers


def create_canary_activation(
    *,
    strategy_id: str,
    strategy_version: str,
    strategy_hash: str,
    config_hash: str,
    dataset_provenance: str,
    broker: str,
    account_hash: str,
    confirmation_phrase: str,
    actor: str,
    capital_limit: float = 2_000.0,
    max_daily_loss: float = 500.0,
    max_position_value: float = 2_000.0,
    max_order_quantity: float = 1.0,
    max_order_value: float = 1_000.0,
    max_orders_per_day: int = 2,
    max_turnover_per_day: float = 2_000.0,
    allowed_instruments: tuple[str, ...] = ("RELIANCE",),
    allowed_sides: tuple[str, ...] = ("BUY",),
    allowed_order_types: tuple[str, ...] = ("MARKET",),
    allowed_products: tuple[str, ...] = ("CNC",),
    ttl_hours: float = 24.0,
    timestamp: datetime | None = None,
    activation_nonce: str | None = None,
) -> CanaryActivationRecord:
    if confirmation_phrase != CANARY_CONFIRM_PHRASE:
        raise ValueError("invalid_confirmation")
    if not strategy_id.strip():
        raise ValueError("strategy_id_required")
    ts = timestamp or datetime.now(timezone.utc)
    exp = ts + timedelta(hours=ttl_hours)
    nonce = activation_nonce or deterministic_id("nonce", strategy_id, ts.isoformat())
    cfg = {
        "strategy_id": strategy_id,
        "strategy_hash": strategy_hash,
        "config_hash": config_hash,
        "capital_limit": capital_limit,
        "max_daily_loss": max_daily_loss,
        "max_order_value": max_order_value,
        "instruments": list(allowed_instruments),
    }
    configuration_hash = state_hash(cfg)
    aid = deterministic_id(
        "canary_act", actor, strategy_id, strategy_hash, config_hash, ts.isoformat()
    )
    return CanaryActivationRecord(
        activation_id=aid,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        dataset_provenance=dataset_provenance,
        broker=broker,
        account_hash=account_hash,
        capital_limit=capital_limit,
        max_daily_loss=max_daily_loss,
        max_position_value=max_position_value,
        max_order_quantity=max_order_quantity,
        max_order_value=max_order_value,
        max_orders_per_day=max_orders_per_day,
        max_turnover_per_day=max_turnover_per_day,
        activation_timestamp=ts.isoformat(),
        expiry_timestamp=exp.isoformat(),
        human_confirmation=confirmation_phrase,
        activation_nonce=nonce,
        configuration_hash=configuration_hash,
        allowed_instruments=tuple(allowed_instruments),
        allowed_sides=tuple(s.upper() for s in allowed_sides),
        allowed_order_types=tuple(t.upper() for t in allowed_order_types),
        allowed_products=tuple(p.upper() for p in allowed_products),
        actor=actor,
        active=True,
    )


def activation_content_hash(record: CanaryActivationRecord) -> str:
    payload = {k: v for k, v in record.to_dict().items() if k != "activation_id"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
