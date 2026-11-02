"""YallaSell – demonstration of stage 1 and stage 2.

    python3 main.py                 offline: Israeli holidays from data/demo_holidays.json (SIMULATED)
    python3 main.py --live          real Israeli holidays from the Hebcal service (network)
    python3 main.py --stage2-only   skip the stage 1 part
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import date
from itertools import islice
from pathlib import Path

from yallasell import iterators, processing
from yallasell.api_client import CalendarConnectionError, FileCalendarClient, HebcalClient
from yallasell.async_processing import (SimulatedPlatforms, StatusRequest, ads_needing_attention,
                                        collect_concurrent, collect_sequential)
from yallasell.config import load_settings, setup_logging
from yallasell.context_managers import ReviewSession
from yallasell.models import Client, Marketplace, OwnCatalog, Sale, SaleAgreement
from yallasell.observers import ClientNotifier, ListingCloser, SaleEvents, SalesStatistics
from yallasell.repository import ItemRepository
from yallasell.services import AgreementScheduler, PublishingService, SalesService
from yallasell.strategies import StandardPricing, UrgentDiscountPricing
from yallasell.threaded_processing import PurchaseDesk, run_buyers

DATA_FILE = Path(__file__).parent / "data" / "sample_data.jsonl"
DEMO_HOLIDAYS_FILE = Path(__file__).parent / "data" / "demo_holidays.json"
TODAY = date.today()

# New agreements signed in March 2027, 30 days each: their end dates fall around Pesach.
NEW_AGREEMENTS = [("A-201", "Yael Katz", "Netanya", date(2027, 4, 22)),     # Pesach I (Thursday)
                  ("A-202", "Omer Biton", "Ashdod", date(2027, 4, 28)),     # Pesach VII (Wednesday)
                  ("A-203", "Dana Levi", "Holon", date(2027, 4, 30)),       # Friday
                  ("A-204", "Ron Azulay", "Haifa", date(2027, 5, 5))]       # ordinary Wednesday


def title(text: str) -> None:
    print(f"\n{'=' * 64}\n{text}\n{'=' * 64}")


def stage1() -> None:
    # ------------------------------------------------------------ 1. load the file
    title("1. Loading data/sample_data.jsonl line by line")
    repo = ItemRepository.from_jsonl(DATA_FILE)
    print(repo)
    for line_number, reason in repo.errors:
        print(f"  rejected line {line_number}: {reason}")
    items = repo.items
    agreement_of = processing.agreement_by_item(repo.agreements)

    # ------------------------------------------------------------ 2. OOP
    title("2. OOP: composition, inheritance, polymorphism, validation")
    agreement = repo.agreements["A-108"]
    print(agreement, f"| len = {len(agreement)} | total asked = {agreement.total_asking_value:.0f} ₪")
    print("Same method on different types (no if/elif on the type):")
    for item in agreement.items:
        print(f"  {type(item).__name__:<12} {item.title:<32} suggested {item.suggested_price():>5} ₪"
              f"  commission {item.commission_rate():.0%}")
    print("Each channel writes its own ad:")
    camera = repo.get(215)
    for channel in (OwnCatalog(), Marketplace("Marketplace A", 0.10), Marketplace("Marketplace B", 0.12, 20)):
        print("  ", channel.publish(camera))
    sale = Sale(repo.get(211), Marketplace("Marketplace A", 0.10), 330)
    print("Sale:", sale)
    try:
        repo.get(201).change_status("submitted")
    except ValueError as error:
        print("Refused status change:", error)

    # ------------------------------------------------------------ 3. FIFO queue
    title("3. Review queue – deque, first in first out")
    queue = processing.build_review_queue(items)
    print("Waiting:", [item.item_id for item in queue])
    while (item := processing.next_for_review(queue)) is not None:
        print(f"  reviewing #{item.item_id} {item.title}")
    print("Empty queue ->", processing.next_for_review(queue), "(no crash)")

    # ------------------------------------------------------------ 4. priority queue
    title("4. Urgent items – heapq, fewer days left = handled first")
    heap = processing.build_urgency_heap(agreement_of, items, TODAY)
    print(f"Heap size {len(heap)}; heap[0] is the most urgent, the rest is not sorted")
    for _ in range(3):
        days_left, item = processing.pop_most_urgent(heap)
        print(f"  {days_left:>3} days left  #{item.item_id} {item.title}")

    # ------------------------------------------------------------ 5. dict
    title("5. Dictionaries – index by id and counting")
    index = processing.index_by_id(items)
    print("index[209] ->", index[209].title)
    print("index.get(999) ->", index.get(999), "(missing id is expected, no KeyError)")
    try:
        processing.index_by_id(items + [index[201]])
    except ValueError as error:
        print("Adding an existing id is refused:", error)
    for category, count in processing.count_by_category(items).items():   # unpacking in for
        print(f"  {category:<12} {count} items")
    for status, total in processing.value_by_status(items).items():
        print(f"  {status:<10} {total:>7.0f} ₪ asked")

    # ------------------------------------------------------------ 6. set
    title("6. Sets – unique values and set operations")
    cats = processing.categories(items)
    print("Categories (order not guaranteed):", sorted(cats))
    print("'furniture' in categories ->", "furniture" in cats)
    cats.add("books")
    cats.discard("toys")                     # discard: no error if missing
    try:
        cats.remove("toys")                  # remove: KeyError if missing
    except KeyError:
        print("remove('toys') raised KeyError, discard('toys') did not")
    sold = processing.clients_with_status(repo.agreements, "sold")
    listed = processing.clients_with_status(repo.agreements, "listed")
    print("Sold AND still have listed items (intersection):", sorted(sold & listed))
    print("Only listed, nothing sold yet (difference):   ", sorted(listed - sold))

    # ------------------------------------------------------------ 7. list, tuple, comprehensions, sorting
    title("7. Lists, tuples, comprehensions and sorting")
    rows = processing.summary_rows(items[:3])
    print("Tuples (id, title, price):", rows)
    item_id, item_title, *_ = rows[0]        # unpack a tuple, ignore the rest
    print(f"First row unpacked -> id={item_id}, title={item_title}")
    cheapest, others = processing.cheapest_and_others(items)
    print(f"cheapest, *others -> {cheapest.title} ({cheapest.asking_price:.0f} ₪) + {len(others)} others")
    print("Listed (list comprehension):", [i.item_id for i in processing.listed_items(items)])
    print("id -> title (dict comprehension):", {i.item_id: i.title for i in items[:3]})
    print("By price (lambda):", [i.item_id for i in processing.by_price(items)][:6], "...")
    print("By category then price (tuple key):")
    for item in processing.by_category_then_price(items)[:5]:
        print(f"   {item.category:<12} {item.asking_price:>6.0f} ₪  {item.title}")
    best = processing.by_expected_payout(items)[0]
    print(f"Best expected payout (regular function as key): {best.title}"
          f" -> {processing.expected_payout(best):.0f} ₪")

    # ------------------------------------------------------------ 8. Iterable / Iterator
    title("8. Custom Iterable + Iterator – two independent traversals")
    catalog = iterators.ItemCatalog(items[:4])
    first, second = iter(catalog), iter(catalog)
    print("first :", next(first).item_id, next(first).item_id, next(first).item_id)
    print("second:", next(second).item_id, "(starts again from the beginning)")
    print("first continues:", next(first).item_id)
    try:
        next(first)
    except StopIteration:
        print("first is finished -> StopIteration")

    # ------------------------------------------------------------ 9. generator
    title("9. Generator with yield – items buyers can purchase")
    ready = iterators.items_ready_for_buyers(items)
    print("Generator created, nothing processed yet:", ready)
    print("next() ->", next(ready).item_id)
    print("for continues where it stopped ->", [item.item_id for item in ready])
    print("Second loop on the same generator ->", list(ready), "(exhausted: create a new one)")

    # ------------------------------------------------------------ 10. lazy pipeline
    title("10. Lazy pipeline – listed -> price <= 500 ₪ -> id, only the first 2")
    read_log: list[int] = []
    pipeline = iterators.affordable_listed_ids(iterators.watched(items, read_log), 500)
    print("Pipeline built, items read so far:", read_log)
    print("First 2 results:", list(islice(pipeline, 2)))
    print(f"Items actually read: {read_log} -> {len(items) - len(read_log)} of {len(items)} never processed")

    # ------------------------------------------------------------ 11. context manager
    title("11. Context manager – ReviewSession")
    camera = repo.get(207)
    with ReviewSession(camera) as item:
        print(f"inside:  #{item.item_id} is {item.status}")
        item.change_status("approved")                 # decision taken -> kept
    print(f"after:   #{camera.item_id} is {camera.status} (decision kept)")

    coat = repo.get(203)
    session = ReviewSession(coat)
    try:
        with session as item:
            print(f"inside:  #{item.item_id} is {item.status}")
            raise RuntimeError("reviewer's computer crashed")
    except RuntimeError as error:
        print(f"exception reached the caller: {error}")
    print(f"after:   #{coat.item_id} is {coat.status} (restored: {session.restored})")


# ==================================================================== STAGE 2

class SimulatedOutage:
    """Stands for the calendar service being down. Used ONLY in section 13, always labelled."""

    def get_holidays(self, start, end):
        raise CalendarConnectionError("SIMULATED outage: calendar service unreachable after 3 attempts")


def new_agreements() -> list[SaleAgreement]:
    return [SaleAgreement(aid, Client(100 + n, name, city), end)
            for n, (aid, name, city, end) in enumerate(NEW_AGREEMENTS, start=1)]


def stage2(live: bool) -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    if live:
        calendar_client = HebcalClient(settings.calendar_api_url, settings.calendar_timeout,
                                       settings.calendar_max_attempts, settings.calendar_retry_wait)
        mode = f"LIVE – real Israeli holidays from {settings.calendar_api_url}"
    else:
        calendar_client = FileCalendarClient(DEMO_HOLIDAYS_FILE)
        mode = f"OFFLINE – SIMULATED holidays from data/{DEMO_HOLIDAYS_FILE.name} (use --live for real data)"

    # ------------------------------------------------------------ 12. external service
    title(f"12. Stage 2 – end dates on business days only – mode: {mode}")
    agreements = new_agreements()
    report = AgreementScheduler(calendar_client).schedule(agreements)    # dependency from outside
    print(report.summary())
    if report.calendar:
        for holiday in sorted(report.calendar.holidays.values(), key=lambda h: h.day):
            print(f"  Yom Tov from the calendar: {holiday.day} {holiday.title} ({holiday.hebrew})")
    for agreement, old, new, reasons in report.moved:
        print(f"  {agreement.agreement_id} {agreement.client.name:<11} {old} -> {new}   because: {'; '.join(reasons)}")
    for agreement in report.confirmed:
        print(f"  {agreement.agreement_id} {agreement.client.name:<11} {agreement.end_date} confirmed (business day)")

    # ------------------------------------------------------------ 13. failure policy
    title("13. Failure policy – calendar service down (SIMULATED outage, not real data)")
    agreements = new_agreements()
    outage = AgreementScheduler(SimulatedOutage()).schedule(agreements)
    print(outage.summary())
    for agreement, proposal in outage.pending:
        print(f"  {agreement.agreement_id} end date kept {agreement.end_date} – "
              f"weekend-only proposal {proposal}, holidays NOT checked -> pending")
    print("  No end date was changed or confirmed with incomplete information.")

    # ------------------------------------------------------------ 14. strategy + publishing
    repo = ItemRepository.from_jsonl(DATA_FILE)            # fresh objects, independent of stage 1
    agreement_of = processing.agreement_by_item(repo.agreements)
    channels = [OwnCatalog(), Marketplace("Marketplace A", 0.10), Marketplace("Marketplace B", 0.12, 20)]
    title("14. Strategy – price policy, then publishing on 3 Israeli channels")
    to_publish = []
    for item_id in (207, 214, 217):                         # new requests whose agreement is running
        item = repo.get(item_id)
        with ReviewSession(item):
            item.change_status("approved")
        to_publish.append((item, agreement_of[item_id].days_left(TODAY)))
    standard, urgent = StandardPricing(), UrgentDiscountPricing(threshold_days=21, discount=0.15)
    for item, days in to_publish:
        print(f"  #{item.item_id} {item.title:<34} {days:>4} days  "
              f"standard {standard.price(item, days):>5} ₪   urgent policy {urgent.price(item, days):>5} ₪")
    publisher = PublishingService(urgent, channels)         # dependencies from outside
    published = publisher.publish(to_publish)
    print(f"{len(published.published)} ads published, {len(published.skipped)} skipped")
    for listing in published.published:
        print("  ", listing)

    # ------------------------------------------------------------ 15. observer
    title("15. Observer – one sale, three reactions")
    events = SaleEvents()
    stats = SalesStatistics()
    client_of = {item_id: agr.client.name for item_id, agr in agreement_of.items()}
    notifier = ClientNotifier(client_of)
    for observer in (ListingCloser(publisher.listings_by_item), stats, notifier):
        events.subscribe(observer)
    sales = SalesService(events)
    camera_ads = publisher.listings_by_item[207]
    sold_ad = camera_ads[1]                                 # sold on Marketplace A
    sale = sales.sell(sold_ad, sold_ad.price)
    print("Sale:", sale)
    print("  ads of #207 now:", {l.channel.name: l.status for l in camera_ads})
    print("  statistics     :", stats.sales_by_channel, f"commission {stats.total_commission:.2f} ₪")
    print("  message to     :", *notifier.outbox[0], sep="\n    ")

    # ------------------------------------------------------------ 16. async
    title("16. Async – status of 3 ads on 3 platforms (SIMULATED platforms)")
    requests_ = [StatusRequest("Marketplace A", 214), StatusRequest("Marketplace B", 217),
                 StatusRequest("YallaSell catalog", 214)]
    answers = {("Marketplace A", 214): (0.6, "active", 3),
               ("Marketplace B", 217): (0.3, "active", 41),
               ("YallaSell catalog", 214): (0.2, "active", 7)}
    start = time.perf_counter()
    sequential = asyncio.run(collect_sequential(SimulatedPlatforms(answers), requests_))
    t_seq = time.perf_counter() - start
    platforms = SimulatedPlatforms(answers)
    start = time.perf_counter()
    concurrent = asyncio.run(collect_concurrent(platforms, requests_))
    t_con = time.perf_counter() - start
    print(f"sequential {t_seq:.2f}s | gather {t_con:.2f}s | same results: {sequential == concurrent}")
    print("  result order :", [(s.channel, s.item_id) for s in concurrent], "(input order)")
    print("  finish order :", platforms.finish_order)
    for s in ads_needing_attention(concurrent, min_views=10):
        print(f"  few views -> consider a price drop: #{s.item_id} on {s.channel} ({s.views} views)")

    # ------------------------------------------------------------ 17. threads + lock
    title("17. Threads – 3 buyers press 'buy' on the same unique item at the same time")
    action_cam = repo.get(216)
    desk = PurchaseDesk(processing_delay=0.05)
    run_buyers(desk, action_cam, ["buyer on Marketplace A", "buyer on Marketplace B", "buyer on catalog"])
    print(f"confirmed: {len(desk.confirmed)} | refused: {len(desk.refused)} | "
          f"item #{action_cam.item_id} is {action_cam.status}")

    # ------------------------------------------------------------ 18. TDD capability
    title("18. Ended agreements – listed items expire, client is asked (developed with TDD)")
    for agreement in repo.agreements.values():
        for item in agreement.expire_overdue(TODAY):
            print(f"  #{item.item_id} {item.title} -> {item.status}; ask {agreement.client.name}: "
                  f"extend (extend) or take back free (close_unsold)?")
    print(f"\nCalendar used in this run: {'REAL (live)' if live else 'SIMULATED (offline file)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="YallaSell demo")
    parser.add_argument("--live", action="store_true", help="use the real exchange-rate service")
    parser.add_argument("--stage2-only", action="store_true", help="skip the stage 1 demo")
    args = parser.parse_args()
    if not args.stage2_only:
        stage1()
    stage2(live=args.live)


if __name__ == "__main__":
    main()
