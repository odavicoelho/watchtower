from datetime import UTC, datetime, timedelta
from decimal import Decimal

from watchtower import dashboard
from watchtower.models import Record
from watchtower.rules import Alert
from watchtower.storage import Storage

DAY = datetime(2026, 10, 21, 9, tzinfo=UTC)


def seeded() -> Storage:
    db = Storage(":memory:")
    for i, price in enumerate(["5.00", "5.10", "4.95"]):
        when = DAY + timedelta(days=i)
        run = db.start_run(when)
        db.save(
            [Record(source="bcb_ptax", key="USD", name="US dollar", value=Decimal(price), unit="BRL")],
            run,
            when,
        )
        db.finish_run(run, when, "ok")
    db.save_alerts(
        [Alert("threshold", "bcb_ptax", "USD", "<b>US dollar</b>", "fell below 5 BRL")], run, "2026-10-23"
    )
    return db


def test_sparkline_scales_to_the_box() -> None:
    assert dashboard.sparkline([Decimal(1), Decimal(3)], width=100, height=40) == "M0.0,40.0 L100.0,0.0"
    assert dashboard.sparkline([Decimal(2), Decimal(2)], width=100, height=40) == "M0.0,20.0 L100.0,20.0"
    assert dashboard.sparkline([Decimal(1)]) == ""


def test_renders_tiles_stats_and_alerts() -> None:
    html = dashboard.render(seeded(), now=DAY)

    assert "Exchange rates" in html
    assert "4.9500" in html  # latest value
    assert "-2.94%" in html  # vs previous day
    assert "<path d=" in html
    assert "fell below 5 BRL" in html


def test_content_is_html_escaped() -> None:
    html = dashboard.render(seeded(), now=DAY)
    assert "&lt;b&gt;US dollar&lt;/b&gt;" in html
    assert "<b>US dollar</b>" not in html


def test_empty_database_still_renders() -> None:
    html = dashboard.render(Storage(":memory:"), now=DAY)
    assert "No alerts yet" in html
