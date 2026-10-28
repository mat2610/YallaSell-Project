"""Threads and a shared resource: several buyers want the SAME second-hand item.

An item published on several platforms is unique: there is only one. If two buyers
on two platforms press "buy" at the same moment, only one purchase may be confirmed.

A purchase is: check the item is 'listed' -> take the payment and confirm -> mark it 'sold'.

The dangerous order WITHOUT a lock:
  1. thread A checks: item is 'listed'            -> OK
  2. thread B checks: item is still 'listed'      -> OK   (A has not updated yet)
  3. thread A takes the payment, confirms, marks the item 'sold'
  4. thread B takes the payment and confirms too  -> two buyers paid for one item
     (and B's status change then fails: 'sold' -> 'sold' is not allowed)
The check and the update must therefore run as ONE step, protected by the same Lock.
"""

from __future__ import annotations

import threading
import time

from yallasell.models import Item


class PurchaseDesk:
    """Confirms at most one purchase per item."""

    def __init__(self, lock: threading.Lock | None = None, processing_delay: float = 0.0):
        self.lock = lock if lock is not None else threading.Lock()
        self.processing_delay = processing_delay          # local work between check and update
        self.confirmed: list[str] = []
        self.refused: list[str] = []

    def try_buy(self, item: Item, buyer: str) -> bool:
        with self.lock:                                   # check + update = one protected step
            if item.status != "listed":
                self.refused.append(buyer)
                return False
            if self.processing_delay:
                time.sleep(self.processing_delay)         # simulated payment, no network call here
            self.confirmed.append(buyer)
            item.change_status("sold")
            return True


def run_buyers(desk: PurchaseDesk, item: Item, buyers: list[str]) -> None:
    """Start every buyer thread first, then wait for all of them with join."""
    threads = [threading.Thread(target=desk.try_buy, args=(item, buyer), name=buyer)
               for buyer in buyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
