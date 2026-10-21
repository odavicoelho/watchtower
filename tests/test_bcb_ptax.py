import json
from datetime import date
from decimal import Decimal

import httpx
import respx

from tests.conftest import FIXTURES
from watchtower.http import HttpClient
from watchtower.sources.bcb_ptax import BcbPtax, parse_quotes

QUOTES = json.loads((FIXTURES / "bcb_ptax_usd.json").read_text())["value"]


def test_takes_the_latest_closing_quote() -> None:
    record = parse_quotes("USD", QUOTES)

    assert record is not None
    assert record.key == "USD"
    assert record.name == "US dollar"
    assert record.value == Decimal("5.014")
    assert record.unit == "BRL"
    assert record.attributes["quoted_at"] == "2026-10-20 13:09:36.250006"


def test_intraday_bulletins_alone_give_nothing() -> None:
    intraday = [q for q in QUOTES if q["tipoBoletim"] != "Fechamento"]
    assert parse_quotes("USD", intraday) is None


@respx.mock
def test_fetch_asks_for_each_currency_over_the_last_week(http: HttpClient) -> None:
    respx.get("https://olinda.bcb.gov.br/robots.txt").mock(return_value=httpx.Response(404))
    route = respx.get(url__startswith="https://olinda.bcb.gov.br/olinda/servico/PTAX").mock(
        return_value=httpx.Response(200, json={"value": QUOTES})
    )

    records = BcbPtax(currencies=["USD", "EUR"], today=lambda: date(2026, 10, 21)).fetch(http)

    assert [r.key for r in records] == ["USD", "EUR"]
    first_url = str(route.calls[0].request.url)
    assert "'USD'" in first_url or "%27USD%27" in first_url
    assert "10-14-2026" in first_url and "10-21-2026" in first_url
