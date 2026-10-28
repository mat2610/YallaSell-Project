"""Shared fixtures. Every expected value in the tests is computed by hand from the
business rules (see the comments), never by calling the code under test."""

from __future__ import annotations

from datetime import date

import pytest

from yallasell.api_client import ExchangeRates
from yallasell.models import Electronics, Marketplace, OwnCatalog


@pytest.fixture
def phone():
    # good (0.90), 2 years x 15% = 30% lost -> 0.70  =>  1000 * 0.90 * 0.70 = 630 ₪
    return Electronics(1, "Phone", "good", 2, 1000, "Acme", 64, status="approved")


@pytest.fixture
def demo_rates():
    return ExchangeRates("ILS", date(2026, 10, 27), {"USD": 0.27, "EUR": 0.25}, source="simulated")


@pytest.fixture
def channels():
    return [OwnCatalog(),
            Marketplace("GlobalMarket", 0.12, currency="USD"),
            Marketplace("EuroBay", 0.10, currency="EUR")]
