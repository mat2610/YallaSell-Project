"""Collections processing: queues, priority, indexes, unique values and sorting."""

from __future__ import annotations

import heapq
from collections import deque
from datetime import date

from yallasell.models import Item, SaleAgreement

# ---------------------------------------------------------------- FIFO review queue (deque)
# Requests are reviewed in the order they arrived: it is fair to the sellers,
# nobody waits longer because someone else submitted after them.


def build_review_queue(items: list[Item]) -> deque[Item]:
    """Put every item waiting for review in a FIFO queue, in arrival order (id order)."""
    queue: deque[Item] = deque()
    for item in sorted(items, key=lambda i: i.item_id):
        if item.status == "submitted":
            queue.append(item)                          # enter at the back
    return queue


def next_for_review(queue: deque[Item]) -> Item | None:
    """Take the oldest request. An empty queue is a normal situation, not a crash."""
    if not queue:
        return None
    return queue.popleft()                              # leave from the front


# ---------------------------------------------------------------- priority queue (heapq)
# Urgency beats arrival time: an item whose agreement ends soon must be handled first
# (price drop or new channel). SMALLER number = MORE urgent (days left before the end).
# Entries are tuples (days_left, item_id, item): when two items have the same days_left,
# the unique item_id breaks the tie, so Python never has to compare two Item objects.


def build_urgency_heap(agreement_of: dict[int, SaleAgreement], items: list[Item],
                       today: date) -> list[tuple[int, int, Item]]:
    heap: list[tuple[int, int, Item]] = []
    for item in items:
        if item.status == "listed":
            days_left = agreement_of[item.item_id].days_left(today)
            heapq.heappush(heap, (days_left, item.item_id, item))
    return heap        # only heap[0] is guaranteed to be the smallest, the list is NOT sorted


def pop_most_urgent(heap: list[tuple[int, int, Item]]) -> tuple[int, Item] | None:
    if not heap:
        return None
    days_left, _item_id, item = heapq.heappop(heap)     # tuple unpacking, _ = value not used
    return days_left, item


# ---------------------------------------------------------------- dict
# 1) index: find an object by its id  2) counting / grouping


def index_by_id(items: list[Item]) -> dict[int, Item]:
    """Decision for an existing id: refuse it (ValueError), never overwrite silently."""
    index: dict[int, Item] = {}
    for item in items:
        if item.item_id in index:
            raise ValueError(f"id {item.item_id} already exists")
        index[item.item_id] = item
    return index


def agreement_by_item(agreements: dict[str, SaleAgreement]) -> dict[int, SaleAgreement]:
    """dict comprehension: item id -> the agreement that contains it."""
    return {item.item_id: agreement for agreement in agreements.values() for item in agreement.items}


def count_by_category(items: list[Item]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.category] = counts.get(item.category, 0) + 1   # get: a new key is expected
    return counts


def value_by_status(items: list[Item]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for item in items:
        totals[item.status] = totals.get(item.status, 0) + item.asking_price
    return totals


# ---------------------------------------------------------------- set


def categories(items: list[Item]) -> set[str]:
    """set comprehension: each category once, whatever the number of items."""
    return {item.category for item in items}


def clients_with_status(agreements: dict[str, SaleAgreement], status: str) -> set[str]:
    names: set[str] = set()
    for agreement in agreements.values():
        if any(item.status == status for item in agreement.items):
            names.add(agreement.client.name)
    return names


# ---------------------------------------------------------------- list, tuple and * unpacking


def summary_rows(items: list[Item]) -> list[tuple[int, str, float]]:
    """list comprehension building fixed records: (id, title, price) tuples."""
    return [(item.item_id, item.title, item.asking_price) for item in items]


def cheapest_and_others(items: list[Item]) -> tuple[Item, list[Item]]:
    """Star unpacking: the first item, and *all the rest* collected in a list."""
    cheapest, *others = sorted(items, key=lambda i: i.asking_price)
    return cheapest, others


def listed_items(items: list[Item]) -> list[Item]:
    """list comprehension used as a filter."""
    return [item for item in items if item.status == "listed"]


# ---------------------------------------------------------------- sorting with functions as values


def expected_payout(item: Item) -> float:
    """Regular function used as a sort key: what the seller gets if sold at the suggested price."""
    return item.suggested_price() * (1 - item.commission_rate())


def by_expected_payout(items: list[Item]) -> list[Item]:
    return sorted(items, key=expected_payout, reverse=True)


def by_price(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda item: item.asking_price)


def by_category_then_price(items: list[Item]) -> list[Item]:
    """Two fields with a tuple: category A→Z, then the most expensive first inside each one."""
    return sorted(items, key=lambda item: (item.category, -item.asking_price))
