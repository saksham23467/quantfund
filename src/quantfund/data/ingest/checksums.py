"""Content hashing for raw immutability and dataset reproducibility."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


def file_checksum(path: Path, *, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return f"{algorithm}:{h.hexdigest()}"


def hash_bytes(data: bytes, *, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    h.update(data)
    return f"{algorithm}:{h.hexdigest()}"


def hash_json(payload: object, *, algorithm: str = "sha256") -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hash_bytes(raw, algorithm=algorithm)


def directory_checksum(root: Path, *, patterns: Iterable[str] | None = None) -> str:
    """Deterministic hash of file contents under root (relative paths sorted)."""
    root = Path(root)
    files: list[Path] = []
    if patterns:
        for pattern in patterns:
            files.extend(sorted(root.glob(pattern)))
    else:
        files = sorted(p for p in root.rglob("*") if p.is_file())
    # Exclude checksum sidecar itself
    files = [p for p in files if p.name != "checksums.sha256"]
    h = hashlib.sha256()
    for path in files:
        rel = path.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return f"sha256:{h.hexdigest()}"


def write_checksums(root: Path, *, label: str = "raw") -> Path:
    root = Path(root)
    digest = directory_checksum(root)
    out = root / "checksums.sha256"
    out.write_text(f"{label} {digest}\n", encoding="utf-8")
    return out


def verify_checksums(root: Path) -> bool:
    root = Path(root)
    path = root / "checksums.sha256"
    if not path.exists():
        raise FileNotFoundError(f"missing checksums at {path}")
    recorded = path.read_text(encoding="utf-8").strip().split()[-1]
    # Temporarily move checksum file logic: directory_checksum excludes checksums.sha256
    current = directory_checksum(root)
    return recorded == current
