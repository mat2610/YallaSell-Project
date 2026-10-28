"""Publishing, failure policy and one full integrated flow.
The rates client is a Mock: the test replaces the dependency, not the service."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from yallasell.api_client import RatesConnectionError
from yallasell.observers import ClientNotifier, ListingCloser, SaleEvents, SalesStatistics
from yallasell.services import PublishingService, SalesService
from yallasell.strategies import StandardPricing


def test_publish_converts_price_for_each_currency(phone, demo_rates, channels):
    rates_client = Mock()
    rates_client.get_rates.return_value = demo_rates
    service = PublishingService(rates_client, StandardPricing(), channels)

    report = service.publish([(phone, 30)])

    prices = {listing.channel.name: listing.price for listing in report.published}
    assert prices == {"YallaSell catalog": 630,      # 630 ₪
                      "GlobalMarket": 170.10,        # 630 * 0.27
                      "EuroBay": 157.50}             # 630 * 0.25
    assert phone.status == "listed"


def test_rates_failure_holds_foreign_ads_only(phone, channels):
    rates_client = Mock()
    rates_client.get_rates.side_effect = RatesConnectionError("down")
    service = PublishingService(rates_client, StandardPricing(), channels)

    report = service.publish([(phone, 30)])

    assert [listing.channel.name for listing in report.published] == ["YallaSell catalog"]
    assert [channel.name for _, channel in report.held] == ["GlobalMarket", "EuroBay"]
    assert phone.status == "listed"                  # still on sale in Israel


def test_full_flow_publish_sell_and_react(phone, demo_rates, channels):
    """Integrated: rates -> strategy -> publish on 3 channels -> sale -> 3 observers."""
    rates_client = Mock()
    rates_client.get_rates.return_value = demo_rates
    publisher = PublishingService(rates_client, StandardPricing(), channels)
    events = SaleEvents()
    stats = SalesStatistics()
    notifier = ClientNotifier({phone.item_id: "Dana Cohen"})
    for observer in (ListingCloser(publisher.listings_by_item), stats, notifier):
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
    assert notifier.outbox == [("Dana Cohen",
                                "Your item 'Phone' was sold on GlobalMarket. You will receive 136.08 USD.")]

    with pytest.raises(ValueError, match="cannot be sold"):          # same ad cannot be sold twice
        sales.sell(usd_listing, 170.10)
