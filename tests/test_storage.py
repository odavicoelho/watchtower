from datetime import UTC, datetime
from decimal import Decimal

from watchtower.models import Record
from watchtower.storage import Storage

DAY1 = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
DAY1_LATER = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
DAY2 = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def book(price: str, in_stock: bool = True) -> Record:
    return Record(
        source="shop",
        key="b1",
        name="Book",
        value=Decimal(price),
        unit="GBP",
        attributes={"in_stock": in_stock},
    )


def test_same_day_rerun_updates_instead_of_duplicating() -> None:
    db = Storage(":memory:")
    db.save([book("10.00")], db.start_run(DAY1), DAY1)
    db.save([book("9.00")], db.start_run(DAY1_LATER), DAY1_LATER)

    history = db.history("shop", "b1")

    assert len(history) == 1
    assert history[0].record.value == Decimal("9.00")


def test_each_day_keeps_its_own_observation() -> None:
    db = Storage(":memory:")
    db.save([book("10.00")], db.start_run(DAY1), DAY1)
    db.save([book("8.50", in_stock=False)], db.start_run(DAY2), DAY2)

    history = db.history("shop", "b1")

    assert [h.observed_on for h in history] == ["2026-10-21", "2026-10-22"]
    assert [h.record.value for h in history] == [Decimal("10.00"), Decimal("8.50")]
    assert history[1].record.attributes == {"in_stock": False}


def test_latest_and_latest_before_a_day() -> None:
    db = Storage(":memory:")
    db.save([book("10.00")], db.start_run(DAY1), DAY1)
    db.save([book("8.50")], db.start_run(DAY2), DAY2)

    assert db.latest("shop")["b1"].record.value == Decimal("8.50")
    assert db.latest("shop", before="2026-10-22")["b1"].record.value == Decimal("10.00")


def test_decimal_values_survive_the_round_trip_exactly() -> None:
    db = Storage(":memory:")
    db.save([book("0.10")], db.start_run(DAY1), DAY1)

    assert db.latest("shop")["b1"].record.value == Decimal("0.10")
