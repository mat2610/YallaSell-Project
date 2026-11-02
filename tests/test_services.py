"""Business days, failure policy, publishing and one full integrated flow.
The calendar client is a Mock: the test replaces the dependency, not the service."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import pytest

from yallasell.api_client import CalendarConnectionError
from yallasell.observers import ClientNotifier, ListingCloser, SaleEvents, SalesStatistics
from yallasell.services import AgreementScheduler, PublishingService, SalesService, next_business_day
from yallasell.strategies import StandardPricing


@pytest.mark.parametrize("day, expected", [
    (date(2027, 4, 29), date(2027, 4, 29)),     # ordinary Thursday: stays
    (date(2027, 4, 30), date(2027, 5, 2)),      # Friday -> Shabbat -> Sunday
    (date(2027, 4, 22), date(2027, 4, 25)),     # Pesach I (Thursday) -> Friday -> Shabbat -> Sunday
])
def test_next_business_day(pesach_calendar, day, expected):
    assert next_business_day(day, pesach_calendar)[0] == expected


def test_scheduler_moves_end_dates_with_one_calendar_call(pesach_calendar, make_agreement):
    calendar_client = Mock()
    calendar_client.get_holidays.return_value = pesach_calendar
    on_pesach, ordinary = make_agreement("A-1", date(2027, 4, 28)), make_agreement("A-2", date(2027, 5, 5))

    report = AgreementScheduler(calendar_client).schedule([on_pesach, ordinary])

    assert on_pesach.end_date == date(2027, 4, 29)                  # Pesach VII -> next day
    assert ordinary.end_date == date(2027, 5, 5)                    # unchanged
    assert report.confirmed == [ordinary]
    calendar_client.get_holidays.assert_called_once_with(date(2027, 4, 28), date(2027, 5, 19))


def test_calendar_failure_changes_no_end_date(make_agreement):
    calendar_client = Mock()
    calendar_client.get_holidays.side_effect = CalendarConnectionError("down")
    friday = make_agreement("A-1", date(2027, 4, 30))

    report = AgreementScheduler(calendar_client).schedule([friday])

    assert friday.end_date == date(2027, 4, 30)                     # not touched
    assert report.pending == [(friday, date(2027, 5, 2))]           # weekend-only proposal, to check later
    assert report.moved == [] and report.confirmed == []
    assert report.calendar_error


def test_full_flow_publish_sell_and_react(phone, channels):
    """Integrated: strategy -> publish on 3 channels -> sale -> 3 observers."""
    publisher = PublishingService(StandardPricing(), channels)
    events = SaleEvents()
    stats = SalesStatistics()
    notifier = ClientNotifier({phone.item_id: "Dana Cohen"})
    for observer in (ListingCloser(publisher.listings_by_item), stats, notifier):
        events.subscribe(observer)
    sales = SalesService(events)

    publisher.publish([(phone, 30)])
    ads = publisher.listings_by_item[1]
    assert [ad.price for ad in ads] == [630, 630, 630]              # same ₪ price everywhere
    sale = sales.sell(ads[1], 630)                                  # sold on Marketplace A

    assert phone.status == "sold"
    assert [ad.status for ad in ads] == ["removed", "sold", "removed"]
    assert sale.commission == 126                                   # electronics 20% of 630
    assert stats.sales_by_channel == {"Marketplace A": 1}
    assert notifier.outbox == [("Dana Cohen",
                                "Your item 'Phone' was sold on Marketplace A. You will receive 504.00 ₪.")]

    with pytest.raises(ValueError, match="cannot be sold"):          # same ad cannot be sold twice
        sales.sell(ads[1], 630)
