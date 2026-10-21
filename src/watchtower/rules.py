"""Change detection: compare each item with its previous observation and decide what deserves an alert.

Rules fire on *transitions* (a price dropping, a value crossing a threshold), never on a steady state,
so a value that stays above a threshold doesn't alert every day.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, ClassVar

from watchtower.models import Record


@dataclass(frozen=True)
class Alert:
    rule: str
    source: str
    key: str
    name: str
    message: str
    url: str | None = None


class Rule(ABC):
    type: ClassVar[str]

    def __init__(self, source: str | None = None, key: str | None = None) -> None:
        # None means "every source" / "every item".
        self.source = source
        self.key = key

    def applies_to(self, record: Record) -> bool:
        return self.source in (None, record.source) and self.key in (None, record.key)

    @abstractmethod
    def check(self, previous: Record | None, current: Record) -> str | None:
        """Return an alert message, or None when nothing noteworthy happened."""

    def evaluate(self, previous: Record | None, current: Record) -> Alert | None:
        if not self.applies_to(current):
            return None
        message = self.check(previous, current)
        if message is None:
            return None
        return Alert(self.type, current.source, current.key, current.name, message, current.url)


class ValueChange(Rule):
    """Value moved by at least `min_percent` in one direction (a price drop, a rate jump...)."""

    def __init__(self, direction: str, min_percent: float, **scope: Any) -> None:
        super().__init__(**scope)
        if direction not in ("up", "down"):
            raise ValueError("direction must be 'up' or 'down'")
        self.direction = direction
        self.min_percent = Decimal(str(min_percent))

    def check(self, previous: Record | None, current: Record) -> str | None:
        if previous is None or previous.value is None or current.value is None or previous.value == 0:
            return None
        change = (current.value - previous.value) / previous.value * 100
        moved = change <= -self.min_percent if self.direction == "down" else change >= self.min_percent
        if not moved:
            return None
        unit = f" {current.unit}" if current.unit else ""
        return f"{previous.value}{unit} → {current.value}{unit} ({change:+.1f}%)"


class PriceDrop(ValueChange):
    type = "price_drop"

    def __init__(self, min_percent: float = 10, **scope: Any) -> None:
        super().__init__("down", min_percent, **scope)


class ValueRise(ValueChange):
    type = "value_rise"

    def __init__(self, min_percent: float = 10, **scope: Any) -> None:
        super().__init__("up", min_percent, **scope)


class NewItem(Rule):
    type = "new_item"

    def check(self, previous: Record | None, current: Record) -> str | None:
        return "new item" if previous is None else None


class StockChange(Rule):
    """An item went out of stock or came back (reads the `in_stock` attribute)."""

    type = "stock_change"

    def check(self, previous: Record | None, current: Record) -> str | None:
        if previous is None:
            return None
        was, now = previous.attributes.get("in_stock"), current.attributes.get("in_stock")
        if was is True and now is False:
            return "out of stock"
        if was is False and now is True:
            return "back in stock"
        return None


class Threshold(Rule):
    """Value crossed above `above` or below `below` (fires once per crossing)."""

    type = "threshold"

    def __init__(self, above: float | None = None, below: float | None = None, **scope: Any) -> None:
        super().__init__(**scope)
        if above is None and below is None:
            raise ValueError("threshold needs 'above' and/or 'below'")
        self.above = None if above is None else Decimal(str(above))
        self.below = None if below is None else Decimal(str(below))

    def check(self, previous: Record | None, current: Record) -> str | None:
        if current.value is None:
            return None
        before = None if previous is None else previous.value
        unit = f" {current.unit}" if current.unit else ""
        if self.above is not None and current.value > self.above and (before is None or before <= self.above):
            return f"rose above {self.above}{unit}: now {current.value}{unit}"
        if self.below is not None and current.value < self.below and (before is None or before >= self.below):
            return f"fell below {self.below}{unit}: now {current.value}{unit}"
        return None


RULES: dict[str, type[Rule]] = {r.type: r for r in (PriceDrop, ValueRise, NewItem, StockChange, Threshold)}


def create(type_name: str, options: dict[str, Any]) -> Rule:
    try:
        cls = RULES[type_name]
    except KeyError:
        raise ValueError(f"unknown rule type {type_name!r}; available: {', '.join(sorted(RULES))}") from None
    return cls(**options)


def evaluate(rules: list[Rule], previous: dict[str, Record], current: list[Record]) -> list[Alert]:
    if not previous:
        # First time this source is seen: today becomes the baseline, otherwise every item is "new".
        return []
    alerts = []
    for record in current:
        before = previous.get(record.key)
        for rule in rules:
            alert = rule.evaluate(before, record)
            if alert is not None:
                alerts.append(alert)
    return alerts
