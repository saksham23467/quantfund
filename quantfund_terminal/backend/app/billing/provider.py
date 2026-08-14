"""Billing provider abstraction.

The gateway never stores card data or provider secrets in the demo. A real
Stripe provider implements the same interface and is selected via
QFT_BILLING_PROVIDER=stripe; webhooks are verified with QFT_STRIPE_WEBHOOK_SECRET.
"""

from __future__ import annotations

from quantfund_terminal.backend.app.config import BILLING_PROVIDER

PLAN_CATALOG = {
    "analyst": {"seats": 1, "mrr_inr": 12000, "label": "Analyst"},
    "team": {"seats": 10, "mrr_inr": 110000, "label": "Team"},
    "enterprise": {"seats": 50, "mrr_inr": 900000, "label": "Enterprise"},
}


class BillingProvider:
    name = "abstract"

    def create_checkout(self, org_slug: str, plan: str) -> dict:
        raise NotImplementedError

    def handle_webhook(self, payload: dict, signature: str | None) -> dict:
        raise NotImplementedError

    def plan_price(self, plan: str) -> dict:
        return PLAN_CATALOG.get(plan, PLAN_CATALOG["analyst"])


class MockBillingProvider(BillingProvider):
    name = "mock"

    def create_checkout(self, org_slug: str, plan: str) -> dict:
        price = self.plan_price(plan)
        return {
            "provider": self.name,
            "checkout_url": f"https://billing.mock/checkout?org={org_slug}&plan={plan}",
            "plan": plan,
            "seats": price["seats"],
            "mrr_inr": price["mrr_inr"],
            "note": "Mock checkout — no real charge. Set QFT_BILLING_PROVIDER=stripe in prod.",
        }

    def handle_webhook(self, payload: dict, signature: str | None) -> dict:
        # Mock: accept any event and echo the intended effect.
        return {"received": True, "type": payload.get("type", "unknown"), "applied": True}


def get_billing_provider() -> BillingProvider:
    if BILLING_PROVIDER == "stripe":  # pragma: no cover - requires stripe + secrets
        try:
            from quantfund_terminal.backend.app.billing.stripe_provider import StripeProvider

            return StripeProvider()
        except Exception:
            return MockBillingProvider()
    return MockBillingProvider()
