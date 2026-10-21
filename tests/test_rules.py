from decimal import Decimal

import pytest

from watchtower import rules
from watchtower.models import Record
from watchtower.rules import NewItem, PriceDrop, StockChange, Threshold, ValueRise


def rec(value: str | None = "10", key: str = "k", source: str = "shop", **attributes: bool) -> Record:
    return Record(
        source=source,
        key=key,
        name=f"Item {key}",
        value=None if value is None else Decimal(value),
        unit="GBP",
        attributes=dict(attributes),
    )


def test_price_drop_fires_at_or_beyond_the_threshold() -> None:
    rule = PriceDrop(min_percent=10)
    assert rule.check(rec("10"), rec("9.00")) == "10 GBP → 9 GBP (-10.0%)"
    assert rule.check(rec("10"), rec("9.50")) is None
    assert rule.check(rec("10"), rec("12")) is None


def test_value_rise_only_fires_upwards() -> None:
    rule = ValueRise(min_percent=5)
    assert rule.check(rec("100"), rec("106")) is not None
    assert rule.check(rec("100"), rec("90")) is None


def test_value_rules_ignore_missing_values_and_new_items() -> None:
    rule = PriceDrop(min_percent=1)
    assert rule.check(None, rec("5")) is None
    assert rule.check(rec(None), rec("5")) is None
    assert rule.check(rec("0"), rec("5")) is None


def test_new_item() -> None:
    assert NewItem().check(None, rec()) == "new item"
    assert NewItem().check(rec(), rec()) is None


def test_stock_transitions() -> None:
    rule = StockChange()
    assert rule.check(rec(in_stock=True), rec(in_stock=False)) == "out of stock"
    assert rule.check(rec(in_stock=False), rec(in_stock=True)) == "back in stock"
    assert rule.check(rec(in_stock=True), rec(in_stock=True)) is None


def test_threshold_fires_once_per_crossing() -> None:
    rule = Threshold(above=5.30)
    assert rule.check(rec("5.20"), rec("5.35")) is not None  # crossed
    assert rule.check(rec("5.35"), rec("5.40")) is None  # still above: no repeat
    assert Threshold(below=5.0).check(rec("5.10"), rec("4.90")) is not None


def test_messages_trim_noisy_decimals() -> None:
    message = PriceDrop(min_percent=1).check(rec("96.46761"), rec("83778.40000"))
    assert message is None  # a rise, not a drop
    assert ValueRise(min_percent=1).check(rec("96.46761"), rec("83778.40000")) == (
        "96.4676 GBP → 83778.4 GBP (+86746.1%)"
    )


def test_threshold_needs_a_bound() -> None:
    with pytest.raises(ValueError):
        Threshold()


def test_scope_limits_a_rule_to_one_source_and_item() -> None:
    rule = PriceDrop(min_percent=10, source="shop", key="a")
    assert rule.evaluate(rec("10", key="a"), rec("5", key="a")) is not None
    assert rule.evaluate(rec("10", key="b"), rec("5", key="b")) is None
    assert rule.evaluate(rec("10", key="a", source="other"), rec("5", key="a", source="other")) is None


def test_first_run_of_a_source_is_a_baseline_without_alerts() -> None:
    assert rules.evaluate([NewItem()], previous={}, current=[rec(key="a"), rec(key="b")]) == []


def test_evaluate_matches_items_by_key() -> None:
    previous = {"a": rec("10", key="a")}
    alerts = rules.evaluate([PriceDrop(), NewItem()], previous, [rec("8", key="a"), rec("3", key="b")])

    assert [(a.rule, a.key) for a in alerts] == [("price_drop", "a"), ("new_item", "b")]


def test_unknown_rule_type_is_a_clear_error() -> None:
    with pytest.raises(ValueError, match="unknown rule type"):
        rules.create("telepathy", {})
