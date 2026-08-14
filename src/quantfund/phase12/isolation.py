"""Phase 12 live isolation — paper path cannot reach live order submission."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.phase11.isolation import (
    FORBIDDEN_PAPER_IMPORTS,
    LiveAdapterRejected,
    module_imports_forbidden,
    require_paper_execution_adapter,
)

# Additional forbidden modules for Phase 12 package source
PHASE12_FORBIDDEN_IMPORTS = FORBIDDEN_PAPER_IMPORTS + (
    "kiteconnect",
    "quantfund.brokers.zerodha.orders",
)


def assert_paper_only_adapter(adapter: Any) -> PaperExecutionAdapter:
    return require_paper_execution_adapter(adapter)


def scan_phase12_package_for_forbidden_imports(package_dir: Path | None = None) -> list[str]:
    """Return forbidden import hits across phase12 Python sources."""
    root = package_dir or Path(__file__).resolve().parent
    hits: list[str] = []
    for path in sorted(root.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        for bad in module_imports_forbidden(src):
            hits.append(f"{path.name}:{bad}")
    return hits


def live_order_count_always_zero(*, live_orders: int) -> None:
    if live_orders != 0:
        raise RuntimeError(f"live_orders_must_be_zero_got_{live_orders}")


__all__ = [
    "LiveAdapterRejected",
    "PHASE12_FORBIDDEN_IMPORTS",
    "assert_paper_only_adapter",
    "scan_phase12_package_for_forbidden_imports",
    "live_order_count_always_zero",
    "module_imports_forbidden",
]
