"""Strategy pattern: how YallaSell sets the price (in ₪) of an item it publishes.

Business need (stage 1 proposal): items whose agreement is about to end get
priority treatment, for example a price drop. The publishing service receives
a pricing strategy from outside, so the pricing policy can change (normal days,
end-of-season sale...) without touching the publishing code, and each policy
can be tested alone.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from yallasell.models import Item


class PricingStrategy(ABC):
    """Common contract: return the price in ₪ to publish."""

    name: str = "pricing"

    @abstractmethod
    def price(self, item: Item, days_left: int) -> int:
        """days_left: days until the item's agreement ends."""


class StandardPricing(PricingStrategy):
    """The price suggested from category, condition and age (stage 1 formula)."""

    name = "standard"

    def price(self, item: Item, days_left: int) -> int:
        return item.suggested_price()


class UrgentDiscountPricing(PricingStrategy):
    """Same price, but a discount when the agreement ends in `threshold_days` days or less,
    so the item has a better chance to be sold before it must be returned to the client."""

    name = "urgent discount"

    def __init__(self, threshold_days: int = 14, discount: float = 0.15):
        if threshold_days < 0:
            raise ValueError("threshold_days cannot be negative")
        if not 0 < discount < 1:
            raise ValueError(f"discount must be between 0 and 1, got {discount!r}")
        self.threshold_days = threshold_days
        self.discount = discount

    def price(self, item: Item, days_left: int) -> int:
        base = item.suggested_price()
        if days_left <= self.threshold_days:
            return round(base * (1 - self.discount))
        return base
