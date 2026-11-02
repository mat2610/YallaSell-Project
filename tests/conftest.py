"""Shared fixtures. Every expected value in the tests is computed by hand from the
business rules (see the comments), never by calling the code under test."""

from __future__ import annotations

from datetime import date

import pytest

from yallasell.api_client import Holiday, HolidayCalendar
from yallasell.models import Client, Electronics, Marketplace, OwnCatalog, SaleAgreement


@pytest.fixture
def phone():
    # good (0.90), 2 years x 15% = 30% lost -> 0.70  =>  1000 * 0.90 * 0.70 = 630 ₪
    return Electronics(1, "Phone", "good", 2, 1000, "Acme", 64, status="approved")


@pytest.fixture
def channels():
    return [OwnCatalog(), Marketplace("Marketplace A", 0.10), Marketplace("Marketplace B", 0.12)]


@pytest.fixture
def pesach_calendar():
    # Israel 2027: Pesach I = Thursday 22/04, Pesach VII = Wednesday 28/04 (both Yom Tov)
    holidays = {date(2027, 4, 22): Holiday(date(2027, 4, 22), "Pesach I", "פסח א׳"),
                date(2027, 4, 28): Holiday(date(2027, 4, 28), "Pesach VII", "פסח ז׳")}
    return HolidayCalendar(date(2027, 4, 15), date(2027, 5, 19), holidays, source="simulated")


@pytest.fixture
def make_agreement():
    def make(agreement_id: str, end: date) -> SaleAgreement:
        return SaleAgreement(agreement_id, Client(1, "Dana Cohen", "Haifa"), end)
    return make
