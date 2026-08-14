"""AI Research Copilot — deterministic intent router.

Translates natural-language research requests into an auditable PLAN: a SQL query
against the documented research schema, a workflow over the EXISTING QuantFund
infrastructure (dataset certification, PIT universe, factor engine, backtester),
and the read-only API calls the terminal will make. It executes nothing on its
own and can never place an order. An LLM can be plugged in later behind the same
`plan()` contract; the deterministic router keeps the investor demo reproducible
and offline-safe.
"""

from quantfund_terminal.copilot.router import CopilotPlan, plan

__all__ = ["CopilotPlan", "plan"]
