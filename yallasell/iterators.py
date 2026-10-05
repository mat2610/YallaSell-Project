"""Custom iteration: an Iterable with its own Iterator, a generator and a lazy pipeline."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from yallasell.models import Item

# ---------------------------------------------------------------- Iterable + separate Iterator


class ItemCatalog:
    """Iterable collection of items. It only STORES the data.

    Every iter(catalog) creates a NEW ItemCatalogIterator, so several loops
    can go over the same catalog at the same time without disturbing each other.
    Traversal rule: items come out in the order they were added.
    """

    def __init__(self, items: Iterable[Item] = ()):
        self._items: list[Item] = list(items)

    def add(self, item: Item) -> None:
        self._items.append(item)

    def __iter__(self) -> ItemCatalogIterator:
        return ItemCatalogIterator(self._items)

    def __len__(self) -> int:
        return len(self._items)


class ItemCatalogIterator:
    """Keeps the traversal STATE: which position comes next."""

    def __init__(self, items: list[Item]):
        self._items = items
        self._position = 0

    def __iter__(self) -> ItemCatalogIterator:
        return self                                     # an iterator is its own iterable

    def __next__(self) -> Item:
        if self._position >= len(self._items):
            raise StopIteration                         # end of the traversal
        item = self._items[self._position]
        self._position += 1
        return item


# ---------------------------------------------------------------- generator with yield


def items_ready_for_buyers(items: Iterable[Item]) -> Iterator[Item]:
    """Gives, one at a time, only the items buyers can purchase now (status 'listed').

    Nothing runs when the generator is created: the body starts at the first next(),
    pauses at each yield and continues from that exact point on the following next().
    """
    for item in items:
        if item.status == "listed":
            yield item


# ---------------------------------------------------------------- lazy pipeline


def watched(items: Iterable[Item], log: list[int]) -> Iterator[Item]:
    """Pass items through unchanged, but write down each id actually read.
    Used to PROVE which items the lazy pipeline processed."""
    for item in items:
        log.append(item.item_id)
        yield item


def affordable_listed_ids(items: Iterable[Item], max_price: float) -> Iterator[int]:
    """Three chained generator expressions, no list in between:
    1. keep listed items  2. keep those at or under max_price  3. return only the id."""
    listed = (item for item in items if item.status == "listed")
    affordable = (item for item in listed if item.asking_price <= max_price)
    return (item.item_id for item in affordable)
