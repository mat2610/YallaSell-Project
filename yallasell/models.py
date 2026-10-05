"""Business model of YallaSell: clients, items, agreements, channels, listings and sales."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta

# Allowed values shared by several classes
CONDITIONS = {"new": 1.00, "like_new": 0.95, "good": 0.90, "fair": 0.75}  # condition -> price factor

# Item life cycle: which status can follow which
ALLOWED_TRANSITIONS = {
    "submitted": {"in_review"},
    "in_review": {"approved", "rejected", "submitted"},
    "approved": {"listed"},
    "listed": {"sold", "expired"},
    "expired": {"listed", "returned"},   # client says yes -> listed again, no -> returned
    "sold": set(),
    "rejected": set(),
    "returned": set(),
}


# ---------------------------------------------------------------- Client

class Client:
    """A person who wants YallaSell to sell items for them."""

    def __init__(self, client_id: int, name: str, city: str):
        self.client_id = client_id
        self.name = name
        self.city = city

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Client name cannot be empty")
        self._name = value.strip()

    @classmethod
    def from_dict(cls, data: dict) -> Client:
        return cls(data["client_id"], data["name"], data["city"])

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"

    def __repr__(self) -> str:
        return f"Client(client_id={self.client_id}, name={self.name!r}, city={self.city!r})"


# ---------------------------------------------------------------- Items

class Item(ABC):
    """Abstract base class: an item submitted for sale.

    Every item type has its own specific fields, commission and depreciation.
    """

    def __init__(self, item_id: int, title: str, condition: str,
                 years_owned: float, asking_price: float, status: str = "submitted"):
        self.item_id = item_id
        self.title = title
        self.condition = condition
        self.years_owned = years_owned
        self.asking_price = asking_price
        if status not in ALLOWED_TRANSITIONS:
            raise ValueError(f"Unknown status {status!r}")
        self._status = status

    # ---- validated fields

    @property
    def condition(self) -> str:
        return self._condition

    @condition.setter
    def condition(self, value: str) -> None:
        if not self.is_valid_condition(value):
            raise ValueError(f"Invalid condition {value!r}, expected one of {sorted(CONDITIONS)}")
        self._condition = value

    @property
    def asking_price(self) -> float:
        return self._asking_price

    @asking_price.setter
    def asking_price(self, value: float) -> None:
        if not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"Asking price must be a positive number, got {value!r}")
        self._asking_price = float(value)

    @property
    def years_owned(self) -> float:
        return self._years_owned

    @years_owned.setter
    def years_owned(self, value: float) -> None:
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"Years owned cannot be negative, got {value!r}")
        self._years_owned = value

    # ---- status (life cycle)

    @property
    def status(self) -> str:
        return self._status

    def change_status(self, new_status: str) -> None:
        """Move the item to a new status, only if the business process allows it."""
        if new_status not in ALLOWED_TRANSITIONS[self._status]:
            raise ValueError(f"Item {self.item_id}: cannot go from {self._status!r} to {new_status!r}")
        self._status = new_status

    @staticmethod
    def is_valid_condition(value: str) -> bool:
        """Helper also used when checking raw data before building an item."""
        return value in CONDITIONS

    # ---- polymorphic behaviour: each subclass decides

    @property
    @abstractmethod
    def category(self) -> str: ...

    @abstractmethod
    def commission_rate(self) -> float:
        """Share of the sale price kept by YallaSell."""

    @abstractmethod
    def yearly_depreciation(self) -> float:
        """How much value the item loses per year of use (0.10 = 10%)."""

    @abstractmethod
    def details(self) -> str:
        """Type-specific description used in ads."""

    # ---- shared logic that relies on the polymorphic methods

    def suggested_price(self) -> int:
        """Recommended price, from condition and age. Same formula, different result per type."""
        age_factor = max(0.4, 1 - self.yearly_depreciation() * self.years_owned)
        return round(self.asking_price * CONDITIONS[self.condition] * age_factor)

    # ---- alternative constructor: builds the right subclass from a dict

    @classmethod
    def from_dict(cls, data: dict) -> Item:
        item_class = ITEM_TYPES.get(data.get("category"))
        if item_class is None:
            raise ValueError(f"Unknown category {data.get('category')!r}")
        return item_class.from_dict(data)

    def __str__(self) -> str:
        return f"#{self.item_id} {self.title} [{self.category}, {self.condition}] {self.asking_price:.0f} ₪ – {self.status}"

    def __repr__(self) -> str:
        return (f"{type(self).__name__}(item_id={self.item_id}, title={self.title!r}, "
                f"condition={self.condition!r}, status={self.status!r})")


class Electronics(Item):
    def __init__(self, item_id, title, condition, years_owned, asking_price, brand: str, storage_gb: int, **kw):
        super().__init__(item_id, title, condition, years_owned, asking_price, **kw)
        if not isinstance(storage_gb, int) or storage_gb <= 0:
            raise ValueError(f"Storage must be a positive number of GB, got {storage_gb!r}")
        self.brand = brand
        self.storage_gb = storage_gb

    category = "electronics"

    def commission_rate(self) -> float:
        return 0.20

    def yearly_depreciation(self) -> float:
        return 0.15   # electronics lose value fast

    def details(self) -> str:
        return f"{self.brand}, {self.storage_gb} GB"

    @classmethod
    def from_dict(cls, data: dict) -> Electronics:
        return cls(data["id"], data["title"], data["condition"], data["years_owned"],
                   data["asking_price"], data["brand"], data["storage_gb"],
                   status=data.get("status", "submitted"))


class Clothing(Item):
    SIZES = ("XS", "S", "M", "L", "XL")

    def __init__(self, item_id, title, condition, years_owned, asking_price, size: str, material: str, **kw):
        super().__init__(item_id, title, condition, years_owned, asking_price, **kw)
        if size not in self.SIZES:
            raise ValueError(f"Invalid size {size!r}, expected one of {self.SIZES}")
        self.size = size
        self.material = material

    category = "clothing"

    def commission_rate(self) -> float:
        return 0.35

    def yearly_depreciation(self) -> float:
        return 0.20

    def details(self) -> str:
        return f"size {self.size}, {self.material}"

    @classmethod
    def from_dict(cls, data: dict) -> Clothing:
        return cls(data["id"], data["title"], data["condition"], data["years_owned"],
                   data["asking_price"], data["size"], data["material"],
                   status=data.get("status", "submitted"))


class Furniture(Item):
    def __init__(self, item_id, title, condition, years_owned, asking_price, width_cm: int, height_cm: int, **kw):
        super().__init__(item_id, title, condition, years_owned, asking_price, **kw)
        if width_cm <= 0 or height_cm <= 0:
            raise ValueError("Furniture dimensions must be positive")
        self.width_cm = width_cm
        self.height_cm = height_cm

    category = "furniture"

    def commission_rate(self) -> float:
        return 0.25

    def yearly_depreciation(self) -> float:
        return 0.05   # furniture keeps its value longer

    def details(self) -> str:
        return f"{self.width_cm}x{self.height_cm} cm"

    @classmethod
    def from_dict(cls, data: dict) -> Furniture:
        return cls(data["id"], data["title"], data["condition"], data["years_owned"],
                   data["asking_price"], data["width_cm"], data["height_cm"],
                   status=data.get("status", "submitted"))


# category name -> class. Used by Item.from_dict instead of an if/elif chain.
ITEM_TYPES = {"electronics": Electronics, "clothing": Clothing, "furniture": Furniture}


# ---------------------------------------------------------------- Agreement (composition)

class SaleAgreement:
    """A client's agreement with YallaSell. It contains the items to sell (composition)."""

    def __init__(self, agreement_id: str, client: Client, end_date: date):
        self.agreement_id = agreement_id
        self.client = client
        self.end_date = end_date
        self._items: dict[int, Item] = {}

    def add_item(self, item: Item) -> None:
        if item.item_id in self._items:
            raise ValueError(f"Item {item.item_id} is already in agreement {self.agreement_id}")
        self._items[item.item_id] = item

    def remove_item(self, item_id: int) -> Item:
        if item_id not in self._items:
            raise ValueError(f"Item {item_id} is not in agreement {self.agreement_id}")
        return self._items.pop(item_id)

    def find_item(self, item_id: int) -> Item | None:
        return self._items.get(item_id)

    @property
    def items(self) -> list[Item]:
        return list(self._items.values())

    @property
    def total_asking_value(self) -> float:
        return sum(item.asking_price for item in self._items.values())

    def days_left(self, today: date) -> int:
        return (self.end_date - today).days

    def is_expired(self, today: date) -> bool:
        return today > self.end_date

    def extend(self, days: int = 30) -> None:
        """Client answered yes: extend the agreement and put expired items back on sale."""
        if days <= 0:
            raise ValueError("Extension must be a positive number of days")
        self.end_date += timedelta(days=days)
        for item in self._items.values():
            if item.status == "expired":
                item.change_status("listed")

    def close_unsold(self) -> list[Item]:
        """Client answered no: expired items are returned, nothing is charged."""
        returned = [item for item in self._items.values() if item.status == "expired"]
        for item in returned:
            item.change_status("returned")
        return returned

    def __len__(self) -> int:
        return len(self._items)

    def __str__(self) -> str:
        return f"Agreement {self.agreement_id} – {self.client.name}, {len(self)} items, ends {self.end_date}"

    def __repr__(self) -> str:
        return f"SaleAgreement({self.agreement_id!r}, client_id={self.client.client_id}, end_date={self.end_date!r})"


# ---------------------------------------------------------------- Sales channels

class SalesChannel(ABC):
    """Somewhere an item can be published."""

    def __init__(self, name: str, fee_rate: float):
        if not 0 <= fee_rate < 1:
            raise ValueError(f"Fee rate must be between 0 and 1, got {fee_rate!r}")
        self.name = name
        self.fee_rate = fee_rate

    @abstractmethod
    def format_ad(self, item: Item) -> str:
        """Each channel writes the ad in its own format."""

    def publish(self, item: Item) -> Listing:
        return Listing(item, self, self.format_ad(item))

    def __str__(self) -> str:
        return f"{self.name} (fee {self.fee_rate:.0%})"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r}, fee_rate={self.fee_rate})"


class OwnCatalog(SalesChannel):
    """YallaSell's own website: full description."""

    def __init__(self):
        super().__init__("YallaSell catalog", 0.0)

    def format_ad(self, item: Item) -> str:
        return (f"{item.title} – {item.details()} – condition: {item.condition}, "
                f"{item.years_owned} years – {item.suggested_price()} ₪")


class Marketplace(SalesChannel):
    """External platform (simulated at this stage): short ads with a length limit."""

    def __init__(self, name: str, fee_rate: float, max_title_length: int = 40):
        super().__init__(name, fee_rate)
        self.max_title_length = max_title_length

    def format_ad(self, item: Item) -> str:
        text = f"{item.title} ({item.details()})"
        return text[: self.max_title_length] + f" | {item.suggested_price()} ₪"


# ---------------------------------------------------------------- Listing and Sale

class Listing:
    """An ad: one item published on one channel."""

    STATUSES = ("active", "removed", "sold")

    def __init__(self, item: Item, channel: SalesChannel, text: str):
        self.item = item
        self.channel = channel
        self.text = text
        self.status = "active"

    def close(self, sold: bool = False) -> None:
        if self.status != "active":
            raise ValueError(f"Listing on {self.channel.name} is already {self.status}")
        self.status = "sold" if sold else "removed"

    def __str__(self) -> str:
        return f"[{self.channel.name}] {self.text} – {self.status}"

    def __repr__(self) -> str:
        return f"Listing(item_id={self.item.item_id}, channel={self.channel.name!r}, status={self.status!r})"


class Sale:
    """A completed sale. Computes the commission and what the client receives."""

    def __init__(self, item: Item, channel: SalesChannel, price: float):
        if price <= 0:
            raise ValueError(f"Sale price must be positive, got {price!r}")
        self.item = item
        self.channel = channel
        self.price = price

    @property
    def commission(self) -> float:
        return round(self.price * self.item.commission_rate(), 2)

    @property
    def payout_amount(self) -> float:
        return round(self.price - self.commission, 2)

    def __lt__(self, other: Sale) -> bool:
        return self.price < other.price

    def __str__(self) -> str:
        return (f"{self.item.title} sold on {self.channel.name} for {self.price:.0f} ₪ – "
                f"commission {self.commission:.0f} ₪, client receives {self.payout_amount:.0f} ₪")

    def __repr__(self) -> str:
        return f"Sale(item_id={self.item.item_id}, channel={self.channel.name!r}, price={self.price})"
