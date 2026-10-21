"""Kraken public market data: live crypto prices (official public API, no key, no robots.txt restrictions)."""

from decimal import Decimal
from typing import Any

from watchtower.http import HttpClient
from watchtower.models import Record
from watchtower.sources.base import Source, register

TICKER = "https://api.kraken.com/0/public/Ticker"
NAMES = {"XBTUSD": "Bitcoin", "ETHUSD": "Ethereum", "SOLUSD": "Solana"}


class KrakenError(Exception):
    """Kraken answered HTTP 200 but reported an error in the body."""


@register
class Kraken(Source):
    name = "kraken"

    def __init__(self, pairs: list[str] | None = None) -> None:
        self.pairs = pairs or ["XBTUSD", "ETHUSD", "SOLUSD"]

    def fetch(self, http: HttpClient) -> list[Record]:
        # One request per pair: Kraken renames pairs in its answer (XBTUSD → XXBTZUSD), so this keeps
        # each record tied to the pair the config asked for.
        return [parse_ticker(pair, http.get(TICKER, params={"pair": pair}).json()) for pair in self.pairs]


def parse_ticker(pair: str, body: dict[str, Any]) -> Record:
    if body.get("error"):
        raise KrakenError(f"{pair}: {', '.join(body['error'])}")
    (ticker,) = body["result"].values()
    last_price = Decimal(ticker["c"][0])
    opened = Decimal(ticker["o"])
    return Record(
        source=Kraken.name,
        key=pair,
        name=NAMES.get(pair, pair),
        url=f"https://pro.kraken.com/app/trade/{pair.lower()}",
        value=last_price,
        unit=pair[-3:],
        attributes={
            "open_today": float(opened),
            "high_24h": float(ticker["h"][1]),
            "low_24h": float(ticker["l"][1]),
            "change_today_pct": round(float((last_price - opened) / opened * 100), 2) if opened else None,
        },
    )
