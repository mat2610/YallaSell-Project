"""Observer pattern: one event (an item is sold) and several independent reactions.

Business need (stage 1, scenario 2): when an item is sold on one channel,
(1) its ads on every other channel must be removed, (2) the sales statistics
are updated and (3) the client is told how much they receive.
The sales service only announces the sale; it does not know who reacts.
A new reaction (e.g. an accounting export) is a new observer, not a change in the service.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from yallasell.models import Listing, Sale

logger = logging.getLogger(__name__)


class SaleObserver(ABC):
    @abstractmethod
    def on_sale(self, sale: Sale, listing: Listing) -> None:
        """Called once for every sale. listing = the ad that was sold."""


class SaleEvents:
    """The subject: keeps the observers and notifies them, in subscription order."""

    def __init__(self):
        self._observers: list[SaleObserver] = []

    def subscribe(self, observer: SaleObserver) -> None:
        self._observers.append(observer)

    def notify(self, sale: Sale, listing: Listing) -> None:
        for observer in self._observers:
            observer.on_sale(sale, listing)


# ---------------------------------------------------------------- the reactions

class ListingCloser(SaleObserver):
    """Marks the sold ad 'sold' and removes the ads of the same item on the other channels."""

    def __init__(self, listings_by_item: dict[int, list[Listing]]):
        self.listings_by_item = listings_by_item           # shared with the publishing side
        self.removed: list[Listing] = []

    def on_sale(self, sale: Sale, listing: Listing) -> None:
        for other in self.listings_by_item.get(sale.item.item_id, []):
            if other.status != "active":
                continue
            if other is listing:
                other.close(sold=True)
            else:
                other.close(sold=False)
                self.removed.append(other)
                logger.info("Removed ad of item %s on %s", sale.item.item_id, other.channel.name)


class SalesStatistics(SaleObserver):
    """Number of sales per channel and per category, and total commission earned (₪)."""

    def __init__(self):
        self.sales_by_channel: dict[str, int] = {}
        self.sales_by_category: dict[str, int] = {}
        self.total_commission: float = 0.0

    def on_sale(self, sale: Sale, listing: Listing) -> None:
        channel, category = sale.channel.name, sale.item.category
        self.sales_by_channel[channel] = self.sales_by_channel.get(channel, 0) + 1
        self.sales_by_category[category] = self.sales_by_category.get(category, 0) + 1
        self.total_commission = round(self.total_commission + sale.commission, 2)


class ClientNotifier(SaleObserver):
    """Prepares the message to the seller. Here the 'outbox' is a list (no real e-mail/SMS)."""

    def __init__(self, client_of_item: dict[int, str]):
        self.client_of_item = client_of_item               # item_id -> client name
        self.outbox: list[tuple[str, str]] = []            # (client name, message)

    def on_sale(self, sale: Sale, listing: Listing) -> None:
        client = self.client_of_item.get(sale.item.item_id, "unknown client")
        message = (f"Your item '{sale.item.title}' was sold on {sale.channel.name}. "
                   f"You will receive {sale.payout_amount:.2f} ₪.")
        self.outbox.append((client, message))
        logger.info("Sale message prepared for item %s", sale.item.item_id)   # no personal data in logs
