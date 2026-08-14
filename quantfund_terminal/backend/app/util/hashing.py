"""Deterministic content hashing for reproducibility proofs."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(obj: Any) -> str:
    """`sha256:<hex>` over a canonical JSON encoding of `obj`."""
    return f"sha256:{sha256_hex(canonical_json(obj))}"
