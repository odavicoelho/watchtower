# Watchtower · Architecture

## What it is
A small, production-style **web monitoring pipeline**. On a schedule, it collects data from websites and APIs, keeps the full history, detects changes (price drops, value jumps, new items, stock changes, thresholds crossed), sends alerts and publishes a dashboard.

## The live deployment
- Runs **daily, automatically, at no cost** on GitHub Actions.
- Three sources:
  1. **Banco Central do Brasil (PTAX)**: official USD and EUR closing rates, from a public JSON API.
  2. **Kraken public API**: BTC, ETH and SOL prices. (CoinGecko was considered first, but its `robots.txt` disallows `/api/v3`, so it was replaced rather than forced.)
  3. **books.toscrape.com**: a bookstore built for scraping practice. HTML scraping with pagination, price and stock tracking.
- A **public dashboard** on GitHub Pages: latest values, price history sparklines, the alert log and the status of the last run.
- **Alerts as GitHub Issues**: GitHub emails everyone watching the repository, with no secrets to manage.

## Architecture

```
            ┌──────────── config.yaml ────────────┐
            │ sources · rules · notifiers          │
            └──────────────────┬───────────────────┘
                               ▼
┌─────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐   ┌──────────────┐
│ Sources │──▶│ Validate │──▶│  Store   │──▶│  Diff + │──▶│   Notify     │
│ (fetch) │   │ normalize│   │ (SQLite) │   │  rules  │   │ GitHub issue │
└─────────┘   └──────────┘   └────┬─────┘   └─────────┘   │ email·webhook│
 HTML / API    pydantic           │ history                │ console      │
 adapters      models             ▼                        └──────────────┘
                            ┌───────────┐
                            │ Dashboard │  static HTML → GitHub Pages
                            └───────────┘
   Scheduler: GitHub Actions cron (daily) · Local: `watchtower run`
```

## Components
| Component | Responsibility | Design choice |
|---|---|---|
| **Source adapters** | Fetch one site or API and return records | One small interface (`fetch() -> list[Record]`) and a registry; a new site plugs in without touching the pipeline |
| **HTTP client** | Every request | Retries with exponential backoff, timeouts, at most one request per second per host, `robots.txt` respected, clear User-Agent |
| **Validation** | Parse and normalize | `pydantic` records with `Decimal` values: bad data fails loudly instead of corrupting the history |
| **Storage** | One observation per item per day, plus a log of every run and alert | **SQLite**: zero setup, one file. Same-day reruns update instead of duplicating |
| **Rules** | Compare each item with its previous day | `price_drop`, `value_rise`, `new_item`, `stock_change`, `threshold`, declared in YAML. They fire on transitions only; a source's first run is a silent baseline |
| **Notifiers** | Deliver alerts | GitHub Issues, SMTP email, webhook (Slack/Discord) and console behind one interface. Secrets only from environment variables; one failing channel never blocks the others |
| **Dashboard** | Static page rebuilt after each run | Jinja2 + inline SVG sparklines: one HTML file, no JavaScript |
| **Scheduler** | Run daily | GitHub Actions cron. The database is restored from, and saved back to, a single-commit `data` branch |

## Reliability
- Each source runs in isolation: a failing site marks the run *partial* without losing the other sources' data.
- Idempotent runs: re-running on the same day never duplicates observations or alerts.
- Each run records its status, duration and item counts per source.
- 48 tests run offline against **recorded HTML/JSON fixtures**, so CI never depends on the network.
- `ruff` and `mypy --strict` in CI.

## Repository layout
```
watchtower/
├── src/watchtower/
│   ├── sources/          # base.py (interface + registry), books_toscrape.py, bcb_ptax.py, kraken.py
│   ├── http.py           # polite HTTP client
│   ├── models.py         # pydantic records
│   ├── storage.py        # SQLite: observations, runs, alerts
│   ├── rules.py          # change detection
│   ├── notifiers.py      # GitHub Issues, email, webhook, console
│   ├── pipeline.py       # one run, end to end
│   ├── dashboard.py      # builds the static page
│   ├── templates/        # dashboard.html
│   └── cli.py            # `watchtower run | report | sources`
├── tests/                # unit tests + recorded fixtures
├── config.yaml           # local configuration
├── config.demo.yaml      # the live deployment
└── .github/workflows/    # ci.yml, daily.yml
```

## Stack
Python 3.12 · httpx · selectolax · pydantic · SQLite · Typer · Jinja2 · pytest · respx · ruff · mypy · GitHub Actions · GitHub Pages
