"""Capability developed with TDD: when an agreement has ended, its unsold ads expire,
so YallaSell knows which clients to ask "extend or take back?"."""

from __future__ import annotations

from datetime import date

import pytest

from yallasell.models import Client, Clothing, Furniture, SaleAgreement


@pytest.fixture
def agreement():
    agreement = SaleAgreement("A-1", Client(1, "Dana Cohen", "Haifa"), date(2026, 10, 20))
    agreement.add_item(Clothing(1, "Coat", "good", 1, 300, "M", "Wool", status="listed"))
    agreement.add_item(Furniture(2, "Chair", "good", 1, 100, 40, 90, status="sold"))
    agreement.add_item(Clothing(3, "Scarf", "new", 0, 80, "S", "Silk", status="listed"))
    return agreement


def test_ended_agreement_expires_only_listed_items(agreement):
    expired = agreement.expire_overdue(date(2026, 10, 21))

    assert [item.item_id for item in expired] == [1, 3]
    assert agreement.find_item(1).status == "expired"
    assert agreement.find_item(2).status == "sold"          # a sold item is not touched


@pytest.mark.parametrize("today", [date(2026, 10, 1), date(2026, 10, 20)])   # last day still counts
def test_running_agreement_changes_nothing(agreement, today):
    assert agreement.expire_overdue(today) == []
    assert agreement.find_item(1).status == "listed"
