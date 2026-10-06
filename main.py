"""YallaSell – full demonstration of stage 1. Run:  python3 main.py"""

from datetime import date
from itertools import islice
from pathlib import Path

from yallasell import iterators, processing
from yallasell.context_managers import ReviewSession
from yallasell.models import Marketplace, OwnCatalog, Sale
from yallasell.repository import ItemRepository

DATA_FILE = Path(__file__).parent / "data" / "sample_data.jsonl"
TODAY = date.today()


def title(text: str) -> None:
    print(f"\n{'=' * 64}\n{text}\n{'=' * 64}")


def main() -> None:
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


if __name__ == "__main__":
    main()
