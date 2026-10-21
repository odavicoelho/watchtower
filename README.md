# Watchtower

[![CI](https://github.com/odavicoelho/watchtower/actions/workflows/ci.yml/badge.svg)](https://github.com/odavicoelho/watchtower/actions/workflows/ci.yml)
[![Daily run](https://github.com/odavicoelho/watchtower/actions/workflows/daily.yml/badge.svg)](https://github.com/odavicoelho/watchtower/actions/workflows/daily.yml)

A small, production-style **web monitoring pipeline**. Every day it collects data from websites and APIs, keeps the full history, detects changes and raises alerts. It runs itself on GitHub Actions for free.

**📊 Live dashboard: [odavicoelho.github.io/watchtower](https://odavicoelho.github.io/watchtower/)** · **🔔 Alerts: [issues](https://github.com/odavicoelho/watchtower/issues)**

It's the kind of system behind "watch these competitor prices", "tell me when this is back in stock" or "save this data to a database every morning". Here it's pointed at three public sources:

| Source | What | How |
|---|---|---|
| **Banco Central do Brasil (PTAX)** | Official USD and EUR exchange rates | Open-data JSON API |
| **Kraken** | Live BTC, ETH and SOL prices | Public market-data API |
| **books.toscrape.com** | Prices and stock of a bookstore catalogue | HTML scraping with pagination (a sandbox site built for scraping) |

## How it works

```
            ┌──────────── config.yaml ────────────┐
            │ sources · rules · notifiers          │
            └──────────────────┬───────────────────┘
                               ▼
┌─────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐   ┌──────────────┐
│ Sources │──▶│ Validate │──▶│  Store   │──▶│  Diff + │──▶│   Notify     │
│ (fetch) │   │ (pydantic│   │ (SQLite, │   │  rules  │   │ GitHub issue │
└─────────┘   │  models) │   │ history) │   └─────────┘   │ email·webhook│
 HTML / API   └──────────┘   └────┬─────┘                 └──────────────┘
 adapters                         ▼
                           ┌────────────┐
                           │ Dashboard  │ static HTML → GitHub Pages
                           └────────────┘
     Scheduler: GitHub Actions (daily) · locally: `watchtower run`
```

- **Sources** are small adapters behind one interface (`fetch() -> list[Record]`). Monitoring a new site means writing one class; nothing else changes.
- **A polite HTTP client:** retries with exponential backoff, at most one request per second per site, respects `robots.txt`, identifies itself.
- **Storage:** SQLite with one observation per item per day. Re-running the same day updates instead of duplicating, and prices are stored as exact decimals.
- **Rules** fire on *transitions*, not states: a price drop, a value crossing a threshold, a new item, out of stock / back in stock. A value that stays above a threshold doesn't alert every day, the first run of a source is a silent baseline, and the same alert is never sent twice.
- **Notifiers:** GitHub Issues (the live demo; GitHub emails watchers), email over SMTP, webhooks (Slack, Discord) and console. Secrets only ever come from environment variables, and one failing channel never blocks the others.
- **Isolation:** each source runs on its own. A broken site marks the run *partial*; everyone else's data is still saved.

## Run it locally

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

watchtower run                # fetch every source in config.yaml once
watchtower report --out site  # build the dashboard into site/index.html
watchtower sources            # list available source types
```

Configuration lives in [`config.yaml`](config.yaml):

```yaml
sources:
  - type: kraken
    options: {pairs: [XBTUSD, ETHUSD]}
rules:
  - type: price_drop
    options: {source: kraken, min_percent: 5}
  - type: threshold
    options: {source: bcb_ptax, key: USD, above: 5.10}
notifiers:
  - type: email
    options: {to: you@example.com}   # needs WATCHTOWER_SMTP_USER / WATCHTOWER_SMTP_PASSWORD
```

## Adding a source

```python
from watchtower.models import Record
from watchtower.sources.base import Source, register

@register
class MyShop(Source):
    name = "my_shop"

    def fetch(self, http):
        data = http.get("https://example.com/api/products").json()
        return [Record(source=self.name, key=p["sku"], name=p["title"], value=p["price"], unit="BRL")
                for p in data]
```

Then list it in `config.yaml` (`- type: my_shop`), and the rules, storage, alerts and dashboard work with it unchanged.

## Quality

- 48 tests, all offline: real pages and API responses are recorded as fixtures, so CI never depends on the network.
- `ruff` (lint and format) and `mypy --strict` on every push ([CI](.github/workflows/ci.yml)).
- The daily job ([daily.yml](.github/workflows/daily.yml)) restores the database from the `data` branch, runs the pipeline, saves the database back, and publishes the dashboard.

## Stack

Python 3.12 · httpx · selectolax · pydantic · SQLite · Typer · Jinja2 · pytest · respx · ruff · mypy · GitHub Actions · GitHub Pages

---

Built by [Davi Coelho](https://davicoelho-comercial.vercel.app), software & data engineer. Design notes in [ARCHITECTURE.md](ARCHITECTURE.md). MIT licensed.
