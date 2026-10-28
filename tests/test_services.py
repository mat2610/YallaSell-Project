"""Publishing, failure policy, observers and one full integrated flow.
The rates client is a Mock: the test replaces the dependency, not the service."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from yallasell.api_client import RatesConnectionError, RatesDataError
from yallasell.models import Clothing, Marketplace
from yallasell.observers import ClientNotifier, ListingCloser, SaleEvents, SalesStatistics
from yallasell.services import PublishingService, SalesService
from yallasell.strategies import StandardPricing


def rates_mock(rates=None, error=None):
    client = Mock()
    if error is not None:
        client.get_rates.side_effect = error
    else:
        client.get_rates.return_value = rates
    return client


def test_publish_converts_price_for_each_currency(phone, demo_rates, channels):
    service = PublishingService(rates_mock(demo_rates), StandardPricing(), channels)

    report = service.publish([(phone, 30)])

    prices = {listing.channel.name: listing.price for listing in report.published}
    assert prices == {"YallaSell catalog": 630,      # 630 ₪
                      "GlobalMarket": 170.10,        # 630 * 0.27
                      "EuroBay": 157.50}             # 630 * 0.25
    assert phone.status == "listed"
    service.rates_client.get_rates.assert_called_once_with("ILS", ["EUR", "USD"])


@pytest.mark.parametrize("error", [RatesConnectionError("down"), RatesDataError("missing rate for USD")])
def test_rates_failure_holds_foreign_ads_only(phone, channels, error):
    service = PublishingService(rates_mock(error=error), StandardPricing(), channels)

    report = service.publish([(phone, 30)])

    assert [listing.channel.name for listing in report.published] == ["YallaSell catalog"]
    assert [channel.name for _, channel in report.held] == ["GlobalMarket", "EuroBay"]
    assert report.rates is None and report.rates_error
    assert phone.status == "listed"                  # still on sale in Israel


def test_only_foreign_channels_and_no_rates_item_stays_approved(phone):
    service = PublishingService(rates_mock(error=RatesConnectionError("down")), StandardPricing(),
                                [Marketplace("GlobalMarket", 0.12, currency="USD")])

    report = service.publish([(phone, 30)])

    assert report.published == []
    assert phone.status == "approved"                # nothing published -> not 'listed'


def test_items_not_approved_are_skipped(demo_rates, channels):
    shirt = Clothing(2, "Shirt", "good", 1, 100, "M", "Cotton")      # still 'submitted'
    service = PublishingService(rates_mock(demo_rates), StandardPricing(), channels)

    report = service.publish([(shirt, 30)])

    assert report.skipped == [shirt]
    assert report.published == []


def test_observer_subscribed_twice_is_refused():
    events = SaleEvents()
    stats = SalesStatistics()
    events.subscribe(stats)
    with pytest.raises(ValueError):
        events.subscribe(stats)


def test_full_flow_publish_sell_and_react(phone, demo_rates, channels):
    """Integrated: rates -> strategy -> publish on 3 channels -> sale -> 3 observers."""
    publisher = PublishingService(rates_mock(demo_rates), StandardPricing(), channels)
    events = SaleEvents()
    closer = ListingCloser(publisher.listings_by_item)
    stats = SalesStatistics()
    notifier = ClientNotifier({phone.item_id: "Dana Cohen"})
    for observer in (closer, stats, notifier):
        events.subscribe(observer)
    sales = SalesService(events)

    publisher.publish([(phone, 30)])
    usd_listing = next(l for l in publisher.listings_by_item[1] if l.currency == "USD")
    sale = sales.sell(usd_listing, usd_listing.price)

    assert phone.status == "sold"
    assert {l.channel.name: l.status for l in publisher.listings_by_item[1]} == {
        "YallaSell catalog": "removed", "GlobalMarket": "sold", "EuroBay": "removed"}
    assert sale.commission == 34.02                  # electronics 20% of 170.10
    assert stats.sales_by_channel == {"GlobalMarket": 1}
    assert stats.commission_by_currency == {"USD": 34.02}
    assert notifier.outbox == [("Dana Cohen",
                                "Your item 'Phone' was sold on GlobalMarket. You will receive 136.08 USD.")]

    with pytest.raises(ValueError, match="cannot be sold"):          # same ad cannot be sold twice
        sales.sell(usd_listing, 170.10)
