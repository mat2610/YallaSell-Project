"""Business services of stage 2.

- AgreementScheduler: an agreement must end on a business day in Israel, so the client
  can be contacted ("extend or take the item back?") and can come to take the item back.
  It uses the Jewish holidays from the external calendar service.
- PublishingService: publishes approved items, at the price given by a pricing strategy.
- SalesService: records a sale and announces it to the observers.

The services receive their dependencies from outside (constructor): the calendar client
(real, offline file, or a Mock in the tests), the pricing strategy and the sale events.
So each part has one job, can be replaced, and can be tested without network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from yallasell.api_client import CalendarError, HolidayCalendar
from yallasell.models import Item, Listing, Sale, SaleAgreement, SalesChannel
from yallasell.observers import SaleEvents
from yallasell.strategies import PricingStrategy

logger = logging.getLogger(__name__)

WEEKEND = {4: "Friday", 5: "Shabbat"}          # date.weekday(): Monday = 0 ... Friday = 4, Saturday = 5
LOOK_AHEAD_DAYS = 14                           # a long holiday + weekend never needs more


# ---------------------------------------------------------------- business days

def closed_reason(day: date, calendar: HolidayCalendar | None) -> str | None:
    """Why this day is not a business day in Israel, or None if it is one."""
    if day.weekday() in WEEKEND:
        return WEEKEND[day.weekday()]
    if calendar is not None:
        holiday = calendar.holiday_on(day)
        if holiday is not None:
            return holiday.title
    return None


def next_business_day(day: date, calendar: HolidayCalendar | None) -> tuple[date, list[str]]:
    """The day itself if it is a business day, otherwise the next one (and the reasons)."""
    reasons: list[str] = []
    while (reason := closed_reason(day, calendar)) is not None:
        reasons.append(f"{day.isoformat()} {reason}")
        day += timedelta(days=1)
    return day, reasons


class CalendarProvider(Protocol):
    """What the scheduler needs from a calendar client (real one, file one or a Mock)."""

    def get_holidays(self, start: date, end: date) -> HolidayCalendar: ...


@dataclass
class ScheduleReport:
    moved: list[tuple[SaleAgreement, date, date, list[str]]] = field(default_factory=list)
    confirmed: list[SaleAgreement] = field(default_factory=list)          # already on a business day
    pending: list[tuple[SaleAgreement, date]] = field(default_factory=list)  # holidays not checked
    calendar: HolidayCalendar | None = None
    calendar_error: str | None = None

    def summary(self) -> str:
        if self.calendar is not None:
            source = (f"{self.calendar.source.upper()} calendar, "
                      f"{len(self.calendar.holidays)} Yom Tov day(s) in range")
        else:
            source = f"NO calendar ({self.calendar_error})"
        return (f"{len(self.moved)} end date(s) moved, {len(self.confirmed)} confirmed, "
                f"{len(self.pending)} pending – {source}")


class AgreementScheduler:
    """Makes sure every agreement ends on a business day.

    Failure policy (business decision): if the holidays cannot be obtained or are invalid,
    NO end date is changed or confirmed. The weekend-only proposal is kept in
    report.pending, to be checked again – an end date that falls on a holiday would mean
    calling the client and returning items on a day when nobody works.
    """

    def __init__(self, calendar_client: CalendarProvider):
        self.calendar_client = calendar_client

    def schedule(self, agreements: list[SaleAgreement]) -> ScheduleReport:
        report = ScheduleReport()
        if not agreements:
            return report
        start = min(a.end_date for a in agreements)
        end = max(a.end_date for a in agreements) + timedelta(days=LOOK_AHEAD_DAYS)
        try:
            report.calendar = self.calendar_client.get_holidays(start, end)   # ONE call for all
        except CalendarError as error:
            report.calendar_error = str(error)
            logger.warning("Holidays unavailable, end dates left unchanged: %s", error)

        for agreement in agreements:
            new_end, reasons = next_business_day(agreement.end_date, report.calendar)
            if report.calendar is None:
                report.pending.append((agreement, new_end))   # weekend known, holidays not
            elif new_end == agreement.end_date:
                report.confirmed.append(agreement)
            else:
                old_end = agreement.end_date
                agreement.end_date = new_end
                report.moved.append((agreement, old_end, new_end, reasons))
        return report


# ---------------------------------------------------------------- publishing

@dataclass
class PublishReport:
    published: list[Listing] = field(default_factory=list)
    skipped: list[Item] = field(default_factory=list)                     # not approved


class PublishingService:
    """Publishes approved items on every channel, at the price chosen by the strategy."""

    def __init__(self, pricing: PricingStrategy, channels: list[SalesChannel]):
        if not channels:
            raise ValueError("at least one channel is needed")
        self.pricing = pricing
        self.channels = channels
        self.listings_by_item: dict[int, list[Listing]] = {}

    def publish(self, entries: list[tuple[Item, int]]) -> PublishReport:
        """entries: (item, days left in its agreement). Only 'approved' items are published."""
        report = PublishReport()
        for item, days_left in entries:
            if item.status != "approved":
                report.skipped.append(item)
                continue
            price = self.pricing.price(item, days_left)
            for channel in self.channels:
                listing = channel.publish(item, price)
                self.listings_by_item.setdefault(item.item_id, []).append(listing)
                report.published.append(listing)
            item.change_status("listed")
        return report


# ---------------------------------------------------------------- sales

class SalesService:
    """Records a sale and announces it. The reactions are the observers' job."""

    def __init__(self, events: SaleEvents):
        self.events = events
        self.sales: list[Sale] = []

    def sell(self, listing: Listing, price: float) -> Sale:
        if listing.status != "active":
            raise ValueError(f"Listing on {listing.channel.name} is {listing.status}, it cannot be sold")
        sale = Sale(listing.item, listing.channel, price)       # validates the price first
        listing.item.change_status("sold")                      # only a 'listed' item can be sold
        self.sales.append(sale)
        self.events.notify(sale, listing)
        return sale
