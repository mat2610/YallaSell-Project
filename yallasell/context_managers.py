"""Context manager used while a reviewer checks an item."""

from __future__ import annotations

from yallasell.models import Item


class ReviewSession:
    """Marks an item 'in_review' inside the with block.

    On exit:
    - if the reviewer made a decision (approved / rejected), that decision is kept;
    - otherwise (review interrupted, or an exception happened) the item goes back
      to its previous status, so it is never stuck 'in_review'.
    The exception is NOT hidden: __exit__ returns False so the caller still sees it.
    """

    def __init__(self, item: Item):
        self.item = item
        self.previous_status: str | None = None
        self.restored = False

    def __enter__(self) -> Item:
        self.previous_status = self.item.status            # saved for the exit
        self.item.change_status("in_review")
        return self.item                                   # value given to "as"

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if self.item.status == "in_review":                # no decision was made
            self.item.change_status(self.previous_status)
            self.restored = True
        return False                                       # never swallow the exception
