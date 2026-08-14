"""Zerodha Kite authentication helpers — secrets never logged or persisted to Git."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from enum import Enum


class ZerodhaEnv(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


SANDBOX_HOST = "https://sandbox.kite.trade"
PRODUCTION_HOST = "https://api.kite.trade"


@dataclass(frozen=True)
class ZerodhaCredentials:
    api_key: str
    api_secret: str
    access_token: str | None = None
    env: ZerodhaEnv = ZerodhaEnv.SANDBOX

    def __repr__(self) -> str:  # pragma: no cover - safety
        return (
            f"ZerodhaCredentials(api_key='***REDACTED***', "
            f"api_secret='***REDACTED***', access_token='***REDACTED***', "
            f"env={self.env!r})"
        )


def parse_zerodha_env(raw: str | None) -> ZerodhaEnv:
    if raw is None or str(raw).strip() == "":
        return ZerodhaEnv.SANDBOX
    key = str(raw).strip().lower()
    if key in {"sandbox", "test"}:
        return ZerodhaEnv.SANDBOX
    if key in {"production", "prod", "live"}:
        return ZerodhaEnv.PRODUCTION
    raise ValueError(f"invalid_zerodha_env:{raw!r}")


def host_for_env(env: ZerodhaEnv) -> str:
    return SANDBOX_HOST if env == ZerodhaEnv.SANDBOX else PRODUCTION_HOST


def load_credentials_from_env(
    env: dict[str, str] | None = None,
) -> ZerodhaCredentials | None:
    """Load credentials from environment. Returns None if incomplete."""
    e = env if env is not None else os.environ
    api_key = (e.get("ZERODHA_API_KEY") or "").strip()
    api_secret = (e.get("ZERODHA_API_SECRET") or "").strip()
    access = (e.get("ZERODHA_ACCESS_TOKEN") or "").strip() or None
    zenv = parse_zerodha_env(e.get("ZERODHA_ENV"))
    if not api_key or not api_secret:
        return None
    return ZerodhaCredentials(
        api_key=api_key,
        api_secret=api_secret,
        access_token=access,
        env=zenv,
    )


def credentials_configured(env: dict[str, str] | None = None) -> bool:
    return load_credentials_from_env(env) is not None


def checksum_for_session(api_key: str, request_token: str, api_secret: str) -> str:
    """Official Kite checksum: sha256(api_key + request_token + api_secret)."""
    payload = f"{api_key}{request_token}{api_secret}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assert_env_credential_separation(
    *,
    zerodha_env: ZerodhaEnv,
    credential_label: str | None,
) -> None:
    """Refuse sandbox credentials labeled production and vice versa.

    ``credential_label`` is an optional explicit tag from secret store metadata
    (e.g. ``sandbox`` / ``production``). When absent, only env enum is trusted.
    """
    if credential_label is None:
        return
    label = credential_label.strip().lower()
    if zerodha_env == ZerodhaEnv.SANDBOX and label in {"production", "prod", "live"}:
        raise ValueError("production_credentials_forbidden_in_sandbox")
    if zerodha_env == ZerodhaEnv.PRODUCTION and label in {"sandbox", "test"}:
        raise ValueError("sandbox_credentials_forbidden_in_production")


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
