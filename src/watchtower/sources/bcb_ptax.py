"""Banco Central do Brasil PTAX: the official daily exchange rates against the real (open data, no key)."""

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from watchtower.http import HttpClient
from watchtower.models import Record
from watchtower.sources.base import Source, register

API = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"
NAMES = {
    "USD": "US dollar",
    "EUR": "Euro",
    "GBP": "British pound",
    "JPY": "Japanese yen",
    "CHF": "Swiss franc",
}
# Weekends and holidays have no bulletin, so look back far enough to always find the latest one.
LOOKBACK_DAYS = 7


@register
class BcbPtax(Source):
    name = "bcb_ptax"

    def __init__(self, currencies: list[str] | None = None, today: Callable[[], date] = date.today) -> None:
        self.currencies = currencies or ["USD", "EUR"]
        self.today = today

    def fetch(self, http: HttpClient) -> list[Record]:
        end = self.today()
        start = end - timedelta(days=LOOKBACK_DAYS)
        records = []
        for currency in self.currencies:
            url = (
                f"{API}/CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
                f"?@moeda='{currency}'&@dataInicial='{start:%m-%d-%Y}'&@dataFinalCotacao='{end:%m-%d-%Y}'&$format=json"
            )
            record = parse_quotes(currency, http.get(url).json()["value"])
            if record is not None:
                records.append(record)
        return records


def parse_quotes(currency: str, quotes: list[dict[str, Any]]) -> Record | None:
    """Latest closing ("Fechamento") quote of the period. Intraday bulletins are ignored."""
    closings = [q for q in quotes if q.get("tipoBoletim") == "Fechamento"]
    if not closings:
        return None
    latest = max(closings, key=lambda q: str(q["dataHoraCotacao"]))
    return Record(
        source=BcbPtax.name,
        key=currency,
        name=NAMES.get(currency, currency),
        url="https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes",
        # Selling rate is the reference used in contracts and invoices.
        value=Decimal(str(latest["cotacaoVenda"])),
        unit="BRL",
        attributes={
            "buy": float(latest["cotacaoCompra"]),
            "quoted_at": str(latest["dataHoraCotacao"]),
        },
    )
