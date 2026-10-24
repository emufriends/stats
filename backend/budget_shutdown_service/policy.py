"""Dependency-free evaluation of one Cloud Billing notification."""

from __future__ import annotations

from typing import Any


def evaluate_budget_notification(
    payload: dict[str, Any], *, currency: str = "EUR", hard_limit: float = 40.0
) -> dict[str, Any]:
    threshold = float(payload.get("alertThresholdExceeded") or 0)
    observed_currency = str(payload.get("currencyCode") or "").upper()
    cost = payload.get("costAmount")
    budget = payload.get("budgetAmount")
    if observed_currency and observed_currency != currency.upper():
        return {
            "action": "ignored_currency_mismatch",
            "currency": observed_currency,
            "expected_currency": currency.upper(),
        }
    amount_exceeded = cost is not None and float(cost) >= hard_limit
    configured_hard_budget = (
        budget is not None and abs(float(budget) - hard_limit) < 0.01 and threshold >= 1.0
    )
    return {
        "action": "stop" if amount_exceeded or configured_hard_budget else "ignored",
        "threshold": threshold,
        "cost": cost,
        "hard_limit": hard_limit,
        "currency": currency.upper(),
    }
