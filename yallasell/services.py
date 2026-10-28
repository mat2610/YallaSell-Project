"""Business services of stage 2: publishing with real exchange rates, and recording sales.

The services receive their dependencies from outside (constructor):
- PublishingService gets a rates client (real, offline file, or a Mock in the tests)
  and a pricing strategy;
- SalesService gets the SaleEvents subject with its observers.
So each part has one job, can be replaced, and can be tested without network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from yallasell.api_client import ExchangeRates, RatesError
from yallasell.models import BASE_CURRENCY, Item, Listing, Sale, SalesChannel
from yallasell.observers import SaleEvents
from yallasell.strategies import PricingStrategy

logger = logging.getLogger(__name__)


class RatesProvider(Protocol):
    """What the service needs from a rates client (real one, file one or a Mock)."""

    def get_rates(self, base: str, symbols: list[str]) -> ExchangeRates: ...


@dataclass
class PublishReport:
    published: list[Listing] = field(default_factory=list)
    held: list[tuple[Item, SalesChannel]] = field(default_factory=list)   # waiting for a valid rate
    skipped: list[Item] = field(default_factory=list)                     # not approved
    rates: ExchangeRates | None = None
    rates_error: str | None = None

    @property
    def listed_item_ids(self) -> list[int]:
        return sorted({listing.item.item_id for listing in self.published})

    def summary(self) -> str:
        if self.rates is not None:
            source = f"{self.rates.source.upper()} rates of {self.rates.rates_date}"
        elif self.rates_error:
            source = f"NO rates ({self.rates_error})"
        else:
            source = "no foreign channel"
        return (f"{len(self.published)} ads published, {len(self.held)} held, "
                f"{len(self.skipped)} items skipped – {source}")


class PublishingService:
    """Publishes approved items on every channel, converting the price for foreign channels.

    Failure policy (business decision): if the rates cannot be obtained or are invalid,
    NO ad is published on a foreign channel – a wrong or old price in another currency
    could sell the item below the client's price. The item is still published on the
    shekel channels, and the foreign ads are kept in report.held to be published later.
    """

    def __init__(self, rates_client: RatesProvider, pricing: PricingStrategy,
                 channels: list[SalesChannel]):
        if not channels:
            raise ValueError("at least one channel is needed")
        self.rates_client = rates_client
        self.pricing = pricing
        self.channels = channels
        self.listings_by_item: dict[int, list[Listing]] = {}

    def _foreign_currencies(self) -> list[str]:
        return sorted({channel.currency for channel in self.channels if channel.is_foreign})

    def _fetch_rates(self, report: PublishReport) -> None:
        currencies = self._foreign_currencies()
        if not currencies:
            return
        try:
            report.rates = self.rates_client.get_rates(BASE_CURRENCY, currencies)
        except RatesError as error:
            report.rates_error = str(error)
            logger.warning("Foreign channels on hold, rates unavailable: %s", error)

    def publish(self, entries: list[tuple[Item, int]]) -> PublishReport:
        """entries: (item, days left in its agreement). Only 'approved' items are published."""
        report = PublishReport()
        self._fetch_rates(report)

        for item, days_left in entries:
            if item.status != "approved":
                report.skipped.append(item)
                continue
            price_ils = self.pricing.price(item, days_left)
            published_now = 0
            for channel in self.channels:
                if channel.is_foreign:
                    if report.rates is None:
                        report.held.append((item, channel))
                        continue
                    price = report.rates.convert(price_ils, channel.currency)
                else:
                    price = price_ils
                listing = channel.publish(item, price)
                self.listings_by_item.setdefault(item.item_id, []).append(listing)
                report.published.append(listing)
                published_now += 1
            if published_now:
                item.change_status("listed")
        return report


class SalesService:
    """Records a sale and announces it. The reactions are the observers' job."""

    def __init__(self, events: SaleEvents):
        self.events = events
        self.sales: list[Sale] = []

    def sell(self, listing: Listing, price: float) -> Sale:
        """price: in the listing's currency."""
        if listing.status != "active":
            raise ValueError(f"Listing on {listing.channel.name} is {listing.status}, it cannot be sold")
        sale = Sale(listing.item, listing.channel, price)       # validates the price first
        listing.item.change_status("sold")                      # only a 'listed' item can be sold
        self.sales.append(sale)
        self.events.notify(sale, listing)
        return sale
