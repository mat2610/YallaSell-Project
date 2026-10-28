from __future__ import annotations

from yallasell.models import Furniture
from yallasell.threaded_processing import PurchaseDesk, run_buyers


def test_unique_item_is_sold_only_once():
    sofa = Furniture(1, "Sofa", "good", 3, 2000, 200, 90, status="listed")
    desk = PurchaseDesk(processing_delay=0.01)      # makes a race likely if the lock were missing
    buyers = [f"buyer-{n}" for n in range(8)]

    run_buyers(desk, sofa, buyers)

    assert len(desk.confirmed) == 1                 # we check HOW MANY, not WHICH thread won
    assert len(desk.refused) == 7
    assert sofa.status == "sold"
