"""Credential references only — Phase 9 Mock never consumes real secrets."""

from __future__ import annotations

import os
import re
from typing import Any


_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|secret|password|token|authorization|credential)",
    re.IGNORECASE,
)


class CredentialProvider:
    """Resolve env-var *names* only. Values never enter audit/artifacts."""

    def __init__(self, *, allow_resolve: bool = False) -> None:
        # Phase 9 v1: do not resolve real secrets for mock/dry-run.
        self.allow_resolve = allow_resolve

    def resolve_ref(self, env_var_name: str) -> str | None:
        if not env_var_name or not env_var_name.isidentifier() and not env_var_name.startswith(
            "QUANTFUND_"
        ):
            # allow QUANTFUND_* names with underscores
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_var_name or ""):
                raise ValueError(f"invalid_credential_ref:{env_var_name!r}")
        if not self.allow_resolve:
            return None
        return os.environ.get(env_var_name)


def redact_secrets(payload: Any) -> Any:
    """Recursively redact secret-looking keys from structures for logs/audit."""
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if _SECRET_KEY_RE.search(str(k)):
                out[k] = "***REDACTED***"
            else:
                out[k] = redact_secrets(v)
        return out
    if isinstance(payload, list):
        return [redact_secrets(x) for x in payload]
    return payload


def assert_no_secrets(payload: Any) -> None:
    redacted = redact_secrets(payload)
    if redacted != payload and isinstance(payload, dict):
        # If redaction changed values, original contained secret-like keys with non-redacted values
        for k, v in payload.items():
            if _SECRET_KEY_RE.search(str(k)) and v not in (None, "", "***REDACTED***"):
                if isinstance(v, str) and len(v) > 0:
                    raise ValueError(f"secret_leak_detected_key:{k}")
