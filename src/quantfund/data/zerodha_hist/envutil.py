"""Load Zerodha env for real historical validation — never log secret values."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


REQUIRED_KEYS = (
    "QUANTFUND_ALLOW_ZERODHA_HISTORICAL",
    "ZERODHA_API_KEY",
    "ZERODHA_API_SECRET",
    "ZERODHA_ACCESS_TOKEN",
)


def load_dotenv_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE loader. Does not print values. Skips comments."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


def merge_env_with_optional_dotenv(
    *,
    env: dict[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> dict[str, str]:
    """Overlay process env with optional .env (process env wins)."""
    base: dict[str, str] = {}
    if dotenv_path is not None:
        base.update(load_dotenv_file(dotenv_path))
    proc = env if env is not None else dict(os.environ)
    base.update({k: str(v) for k, v in proc.items() if v is not None})
    return base


def validate_real_historical_config(env: dict[str, str]) -> dict[str, Any]:
    """Return status without exposing secret values."""
    allow = (env.get("QUANTFUND_ALLOW_ZERODHA_HISTORICAL") or "").strip()
    problems: list[str] = []
    if allow != "1":
        problems.append(
            "QUANTFUND_ALLOW_ZERODHA_HISTORICAL must be 1 for REAL historical API"
        )
    for k in ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN"):
        if not (env.get(k) or "").strip():
            problems.append(f"missing_env:{k}")
    return {
        "ok": len(problems) == 0,
        "allow_flag": allow == "1",
        "api_key_present": bool((env.get("ZERODHA_API_KEY") or "").strip()),
        "api_secret_present": bool((env.get("ZERODHA_API_SECRET") or "").strip()),
        "access_token_present": bool((env.get("ZERODHA_ACCESS_TOKEN") or "").strip()),
        "problems": problems,
    }
