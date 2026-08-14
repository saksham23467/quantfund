"""Architectural isolation: paper runner may only use PaperExecutionAdapter."""

from __future__ import annotations

from typing import Any

from quantfund.paper.execution import PaperExecutionAdapter


class LiveAdapterRejected(TypeError):
    """Raised when a non-paper execution adapter is injected into paper paths."""


def require_paper_execution_adapter(adapter: Any) -> PaperExecutionAdapter:
    """Dependency injection guard — reject live/zerodha submit adapters."""
    if adapter is None:
        raise LiveAdapterRejected("paper_adapter_required")
    if type(adapter) is not PaperExecutionAdapter and not isinstance(
        adapter, PaperExecutionAdapter
    ):
        # Explicitly reject duck-typed live adapters by class name heuristics
        name = type(adapter).__name__
        if "Live" in name or "Zerodha" in name and "Paper" not in name:
            raise LiveAdapterRejected(f"live_adapter_forbidden:{name}")
        if not isinstance(adapter, PaperExecutionAdapter):
            raise LiveAdapterRejected(f"not_paper_execution_adapter:{name}")
    return adapter


FORBIDDEN_PAPER_IMPORTS = (
    "quantfund.brokers.zerodha.orders",
    "quantfund.brokers.zerodha.adapter",
    "quantfund.production.activation",
)


def module_imports_forbidden(source: str) -> list[str]:
    """Static check helper for tests — returns forbidden module prefixes found."""
    import ast

    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for bad in FORBIDDEN_PAPER_IMPORTS:
                if node.module == bad or node.module.startswith(bad + "."):
                    found.append(node.module)
        if isinstance(node, ast.Import):
            for n in node.names:
                for bad in FORBIDDEN_PAPER_IMPORTS:
                    if n.name == bad or n.name.startswith(bad + "."):
                        found.append(n.name)
    return found
