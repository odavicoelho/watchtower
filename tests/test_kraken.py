import json
from decimal import Decimal

import httpx
import pytest
import respx

from tests.conftest import FIXTURES
from watchtower.http import HttpClient
from watchtower.sources.kraken import Kraken, KrakenError, parse_ticker

BODY = json.loads((FIXTURES / "kraken_ticker_xbtusd.json").read_text())


def test_parses_the_last_trade_price() -> None:
    record = parse_ticker("XBTUSD", BODY)

    assert record.key == "XBTUSD"  # the pair we asked for, not Kraken's internal XXBTZUSD
    assert record.name == "Bitcoin"
    assert record.value == Decimal("83778.40000")
    assert record.unit == "USD"
    assert set(record.attributes) == {"open_today", "high_24h", "low_24h", "change_today_pct"}


def test_errors_in_the_body_are_raised() -> None:
    with pytest.raises(KrakenError, match="Unknown asset pair"):
        parse_ticker("NOPE", {"error": ["EQuery:Unknown asset pair"], "result": {}})


@respx.mock
def test_fetch_requests_each_pair(http: HttpClient) -> None:
    respx.get("https://api.kraken.com/robots.txt").mock(return_value=httpx.Response(404))
    route = respx.get("https://api.kraken.com/0/public/Ticker").mock(
        return_value=httpx.Response(200, json=BODY)
    )

    records = Kraken(pairs=["XBTUSD", "ETHUSD"]).fetch(http)

    assert [r.key for r in records] == ["XBTUSD", "ETHUSD"]
    assert [c.request.url.params["pair"] for c in route.calls] == ["XBTUSD", "ETHUSD"]
