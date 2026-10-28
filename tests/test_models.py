"""Stage 1 behaviours that must still work after the stage 2 changes."""

from __future__ import annotations

import pytest

from yallasell.models import Clothing, Electronics, Furniture, OwnCatalog, Sale
from yallasell.repository import ItemRepository


@pytest.mark.parametrize("item, expected", [
    # 1000 * good 0.90 * (1 - 2 years * 0.15) = 630
    (Electronics(1, "Phone", "good", 2, 1000, "Acme", 64), 630),
    # new item, 0 years: no reduction
    (Clothing(2, "Coat", "new", 0, 400, "M", "Wool"), 400),
    # 1000 * fair 0.75 * (1 - 10 years * 0.05) = 375
    (Furniture(3, "Table", "fair", 10, 1000, 100, 80), 375),
])
def test_suggested_price_per_type(item, expected):
    assert item.suggested_price() == expected


def test_item_cannot_be_sold_before_review():
    item = Clothing(4, "Shirt", "good", 1, 50, "S", "Cotton")       # status 'submitted'
    with pytest.raises(ValueError, match="cannot go from 'submitted' to 'sold'"):
        item.change_status("sold")


def test_sale_commission_and_payout():
    coat = Clothing(5, "Coat", "good", 1, 300, "L", "Wool", status="listed")
    sale = Sale(coat, OwnCatalog(), 200)
    assert sale.commission == 70            # clothing: 35% of 200
    assert sale.payout_amount == 130


def test_repository_reads_file_and_reports_bad_lines(tmp_path):
    good = ('{"id": 1, "agreement_id": "A-1", "client_name": "Dana Cohen", "client_city": "Haifa", '
            '"end_date": "2026-12-01", "category": "furniture", "title": "Chair", "condition": "good", '
            '"years_owned": 1, "asking_price": 100, "status": "listed", "width_cm": 40, "height_cm": 90}')
    path = tmp_path / "items.jsonl"
    path.write_text(good + "\n" + '{"id": 2, "title": "broken\n', encoding="utf-8")

    repo = ItemRepository.from_jsonl(path)

    assert len(repo) == 1
    assert repo.get(1).title == "Chair"
    assert repo.errors == [(2, "invalid JSON")]
