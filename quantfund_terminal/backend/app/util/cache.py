"""Tiny cache abstraction. Uses Redis when QFT_REDIS_URL is set, else in-process.

The gateway never *requires* Redis; production points QFT_REDIS_URL at
ElastiCache. This keeps local/demo runs infra-free.
"""

from __future__ import annotations

import json
import time
from typing import Any

from quantfund_terminal.backend.app.config import REDIS_URL

_redis = None
if REDIS_URL:
    try:  # pragma: no cover - only when redis is installed & configured
        import redis  # type: ignore

        _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _redis.ping()
    except Exception:
        _redis = None

_mem: dict[str, tuple[float, str]] = {}


def cache_get(key: str) -> Any | None:
    if _redis is not None:
        raw = _redis.get(key)
        return json.loads(raw) if raw else None
    hit = _mem.get(key)
    if not hit:
        return None
    expires, raw = hit
    if expires and expires < time.time():
        _mem.pop(key, None)
        return None
    return json.loads(raw)


def cache_set(key: str, value: Any, ttl_seconds: int = 60) -> None:
    raw = json.dumps(value, default=str)
    if _redis is not None:
        _redis.setex(key, ttl_seconds, raw)
        return
    _mem[key] = (time.time() + ttl_seconds if ttl_seconds else 0.0, raw)


def cache_backend() -> str:
    return "redis" if _redis is not None else "in_process"
