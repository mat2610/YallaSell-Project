"""The two alternatives of the pricing Strategy (phone fixture: suggested price 630 ₪)."""

from __future__ import annotations

from yallasell.strategies import StandardPricing, UrgentDiscountPricing


def test_standard_pricing_never_discounts(phone):
    assert StandardPricing().price(phone, days_left=0) == 630


def test_urgent_pricing_discounts_only_near_the_end(phone):
    urgent = UrgentDiscountPricing(threshold_days=14, discount=0.20)
    assert urgent.price(phone, days_left=15) == 630          # one day too early: full price
    assert urgent.price(phone, days_left=14) == 504          # limit included: 630 * 0.80
