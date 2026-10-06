"""Load the JSONL data file line by line and turn every line into business objects."""

from __future__ import annotations

import json
from datetime import date

from yallasell.models import Client, Item, SaleAgreement

# Fields every record must have (the type-specific ones are checked by the Item subclasses)
REQUIRED_FIELDS = ("id", "agreement_id", "client_name", "client_city", "end_date",
                   "category", "title", "condition", "years_owned", "asking_price", "status")


class ItemRepository:
    """Keeps every loaded item, agreement and client, and reports the rejected lines."""

    def __init__(self):
        self._items: dict[int, Item] = {}                    # find an item by its id
        self.agreements: dict[str, SaleAgreement] = {}       # find an agreement by its id
        self.clients: dict[str, Client] = {}                 # one Client per name
        self.errors: list[tuple[int, str]] = []              # (line number, reason)

    @classmethod
    def from_jsonl(cls, path: str) -> ItemRepository:
        """Alternative constructor: create a repository already filled from a file."""
        repo = cls()
        repo.load(path)
        return repo

    def load(self, path: str) -> None:
        # The file is read one line at a time: never read() or readlines(),
        # so even a huge file does not have to fit in memory.
        with open(path, encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue                                 # ignore empty lines
                try:
                    self._add_record(json.loads(line))
                except json.JSONDecodeError:
                    self.errors.append((line_number, "invalid JSON"))
                except (ValueError, KeyError) as error:
                    self.errors.append((line_number, str(error)))

    def _add_record(self, data: dict) -> None:
        missing = [field for field in REQUIRED_FIELDS if field not in data]
        if missing:
            raise ValueError(f"missing fields: {', '.join(missing)}")

        # Decision for a duplicate id: the first record wins, the later one is rejected
        if data["id"] in self._items:
            raise ValueError(f"duplicate id {data['id']}")

        item = Item.from_dict(data)          # validation of the item itself (models.py)
        agreement = self._get_agreement(data)
        agreement.add_item(item)
        self._items[item.item_id] = item

    def _get_agreement(self, data: dict) -> SaleAgreement:
        end_date = date.fromisoformat(data["end_date"])      # ValueError if the date is wrong
        agreement = self.agreements.get(data["agreement_id"])
        if agreement is None:                                # first item of this agreement
            client = self.clients.get(data["client_name"])
            if client is None:
                client = Client(len(self.clients) + 1, data["client_name"], data["client_city"])
                self.clients[client.name] = client
            agreement = SaleAgreement.from_dict(data, client)
            self.agreements[agreement.agreement_id] = agreement
        elif agreement.end_date != end_date or agreement.client.name != data["client_name"]:
            raise ValueError(f"agreement {agreement.agreement_id} has a different client or end date")
        return agreement

    def get(self, item_id: int) -> Item | None:
        """Find an item by id. A missing id is a normal case, so None instead of an error."""
        return self._items.get(item_id)

    @property
    def items(self) -> list[Item]:
        return list(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"ItemRepository(items={len(self)}, agreements={len(self.agreements)}, errors={len(self.errors)})"
