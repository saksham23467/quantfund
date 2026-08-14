"""Immutable broker connection snapshot — never includes credentials."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from quantfund.paper.models import state_hash
from quantfund.phase15.models import scrub_secrets
from quantfund.phase16a.capabilities import BrokerCapabilityFlag


def hash_account_identifier(account_id: str) -> str:
    """One-way hash of broker account id for audit (not reversible to id)."""
    raw = (account_id or "").strip().encode("utf-8")
    return "acct:" + hashlib.sha256(raw).hexdigest()[:24]


@dataclass(frozen=True)
class BrokerConnectionSnapshot:
    broker_name: str
    account_id_hash: str
    capability_set: frozenset[str]
    timestamp: datetime
    configuration_hash: str
    provider_id: str = "zerodha_kite"
    env_label: str = "sandbox"
    simulated: bool = True

    def __post_init__(self) -> None:
        # Defensive: forbid credential-like fields by name on the instance dict
        for key in ("api_key", "api_secret", "access_token", "password"):
            if hasattr(self, key):
                raise ValueError("credential_field_forbidden_on_snapshot")

    def to_dict(self) -> dict[str, Any]:
        return scrub_secrets(
            {
                "broker_name": self.broker_name,
                "account_id_hash": self.account_id_hash,
                "capability_set": sorted(self.capability_set),
                "timestamp": self.timestamp.isoformat(),
                "configuration_hash": self.configuration_hash,
                "provider_id": self.provider_id,
                "env_label": self.env_label,
                "simulated": self.simulated,
                "can_place_orders": False,
                "live_trading": False,
            }
        )


def build_connection_snapshot(
    *,
    broker_name: str,
    account_id: str,
    capabilities: Iterable[BrokerCapabilityFlag | str],
    config: dict[str, Any],
    timestamp: datetime | None = None,
    provider_id: str = "zerodha_kite",
    env_label: str = "sandbox",
    simulated: bool = True,
) -> BrokerConnectionSnapshot:
    caps = frozenset(
        c.value if isinstance(c, BrokerCapabilityFlag) else str(c) for c in capabilities
    )
    # Never hash raw secrets into configuration — expect already-safe config keys
    safe_config = scrub_secrets(dict(config))
    return BrokerConnectionSnapshot(
        broker_name=broker_name,
        account_id_hash=hash_account_identifier(account_id),
        capability_set=caps,
        timestamp=timestamp or datetime.now(timezone.utc),
        configuration_hash=state_hash(safe_config),
        provider_id=provider_id,
        env_label=env_label,
        simulated=simulated,
    )
