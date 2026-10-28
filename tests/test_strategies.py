from __future__ import annotations

import pytest

from yallasell.strategies import StandardPricing, UrgentDiscountPricing


@pytest.mark.parametrize("strategy, days_left, expected", [
    (StandardPricing(), 0, 630),                                         # never a discount
    (UrgentDiscountPricing(threshold_days=14, discount=0.20), 30, 630),  # far from the end
    (UrgentDiscountPricing(threshold_days=14, discount=0.20), 14, 504),  # limit: 630 * 0.80
    (UrgentDiscountPricing(threshold_days=14, discount=0.20), -3, 504),  # already late
])
def test_pricing_strategies(phone, strategy, days_left, expected):
    assert strategy.price(phone, days_left) == expected


@pytest.mark.parametrize("discount", [0, 1, 1.5])
def test_urgent_discount_must_be_between_0_and_1(discount):
    with pytest.raises(ValueError):
        UrgentDiscountPricing(discount=discount)
