"""Paper-only activation records — LIVE_TRADING always FALSE.

Distinct from quantfund.production.activation (live). Paper path must never
import or write live ActivationRecord objects.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.paper.models import deterministic_id


PAPER_ACTIVATION_CONFIRM_PHRASE = "I_CONFIRM_CONTROLLED_PAPER_ACTIVATION"


@dataclass(frozen=True)
class PaperActivationRecord:
    """Immutable human activation for controlled simulation paper only."""

    activation_id: str
    operator_id: str
    strategy_id: str
    strategy_version: str
    config_hash: str
    risk_config_hash: str
    market_data_config_hash: str
    timestamp: str
    reason: str
    expires_at: str | None
    paper_only: bool
    live_trading: bool
    confirmation_phrase_used: bool
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "operator_id": self.operator_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "config_hash": self.config_hash,
            "risk_config_hash": self.risk_config_hash,
            "market_data_config_hash": self.market_data_config_hash,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "expires_at": self.expires_at,
            "paper_only": self.paper_only,
            "live_trading": self.live_trading,
            "LIVE_TRADING": self.live_trading,
            "confirmation_phrase_used": self.confirmation_phrase_used,
            "active": self.active,
            "record_kind": "PAPER_ACTIVATION",
        }

    def content_hash(self) -> str:
        payload = {k: v for k, v in self.to_dict().items() if k != "activation_id"}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_paper_activation_record(
    *,
    operator_id: str,
    strategy_id: str,
    strategy_version: str,
    config_hash: str,
    risk_config_hash: str,
    market_data_config_hash: str,
    reason: str,
    confirmation_phrase: str,
    expires_at: str | None = None,
    timestamp: str | None = None,
) -> PaperActivationRecord:
    if confirmation_phrase != PAPER_ACTIVATION_CONFIRM_PHRASE:
        raise ValueError("paper_activation_confirmation_phrase_invalid")
    if not operator_id.strip():
        raise ValueError("operator_id_required")
    if not strategy_id.strip():
        raise ValueError("strategy_id_required")
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    aid = deterministic_id(
        "paper_act",
        operator_id,
        strategy_id,
        strategy_version,
        config_hash,
        ts,
    )
    return PaperActivationRecord(
        activation_id=aid,
        operator_id=operator_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        config_hash=config_hash,
        risk_config_hash=risk_config_hash,
        market_data_config_hash=market_data_config_hash,
        timestamp=ts,
        reason=reason,
        expires_at=expires_at,
        paper_only=True,
        live_trading=False,
        confirmation_phrase_used=True,
        active=True,
    )


def verify_paper_activation_record(
    record: PaperActivationRecord,
    *,
    strategy_id: str | None = None,
    strategy_version: str | None = None,
    now: datetime | None = None,
) -> list[str]:
    blockers: list[str] = []
    if not record.paper_only:
        blockers.append("activation_not_paper_only")
    if record.live_trading:
        blockers.append("activation_live_trading_true_forbidden")
    if not record.active:
        blockers.append("activation_inactive")
    if not record.confirmation_phrase_used:
        blockers.append("activation_missing_confirmation")
    if strategy_id is not None and record.strategy_id != strategy_id:
        blockers.append("activation_strategy_id_mismatch")
    if strategy_version is not None and record.strategy_version != strategy_version:
        blockers.append("activation_strategy_version_mismatch")
    if record.expires_at:
        current = now or datetime.now(timezone.utc)
        try:
            exp = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
            if current > exp:
                blockers.append("activation_expired")
        except ValueError:
            blockers.append("activation_expires_at_invalid")
    return blockers


def write_paper_activation_record(path: Path, record: PaperActivationRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("paper_activation_record_immutable")
    path.write_text(
        json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_paper_activation_record(path: Path) -> PaperActivationRecord:
    data = json.loads(path.read_text(encoding="utf-8"))
    return PaperActivationRecord(
        activation_id=data["activation_id"],
        operator_id=data["operator_id"],
        strategy_id=data["strategy_id"],
        strategy_version=data["strategy_version"],
        config_hash=data["config_hash"],
        risk_config_hash=data["risk_config_hash"],
        market_data_config_hash=data["market_data_config_hash"],
        timestamp=data["timestamp"],
        reason=data["reason"],
        expires_at=data.get("expires_at"),
        paper_only=bool(data.get("paper_only", False)),
        live_trading=bool(data.get("live_trading", True)),
        confirmation_phrase_used=bool(data.get("confirmation_phrase_used", False)),
        active=bool(data.get("active", False)),
    )
