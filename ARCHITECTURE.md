# P2 · Watchtower: architecture proposal

> Status: **approved 2026-10-21.** Milestone 1 done.

## 1. What it is
A small, production-style **web monitoring pipeline**. On a schedule, it collects data from websites and APIs, stores the full history, detects changes (price drops, new items, items out of stock, value thresholds), sends alerts, and publishes a public dashboard.

**Why this project:** it's what the most common small freelance jobs ask for: "scrape this site", "watch these prices", "alert me when X changes", "save it to a spreadsheet or database". A client sees it running live and thinks "I need exactly that, for my site".

## 2. What the demo will show (live and public)
- Runs **daily, automatically, for free** on GitHub Actions
- Three real sources:
  1. **books.toscrape.com**, a site made for scraping practice, so there are no terms-of-service issues: HTML scraping, pagination, price and stock tracking
  2. **Banco Central do Brasil (PTAX)** USD and EUR rates, a free public API: JSON source with threshold alerts
  3. **Kraken public API** BTC, ETH and SOL prices: data that really changes, so alerts fire in the live demo. CoinGecko was the first choice, but its robots.txt disallows `/api/v3`.
- A **public dashboard** (static page on GitHub Pages): latest values, price history charts, a change log, and "last run / runs so far" as proof it's alive
- **Alerts** when a rule fires (see decision 3)

## 3. Architecture

```
            ┌──────────── config.yaml ────────────┐
            │ sources · rules · notifiers          │
            └──────────────────┬───────────────────┘
                               ▼
┌─────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐   ┌─────────┐
│ Sources │──▶│ Validate │──▶│  Store   │──▶│  Diff + │──▶│ Notify  │
│ (fetch) │   │ normalize│   │ (SQLite) │   │  rules  │   │ GH issue│
└─────────┘   └──────────┘   └────┬─────┘   └─────────┘   │ webhook │
 HTML / API    pydantic           │ history                │ console │
 adapters      models             ▼                        └─────────┘
                            ┌───────────┐
                            │ Dashboard │  static HTML → Vercel
                            └───────────┘
   Scheduler: GitHub Actions cron (daily) · Local: `watchtower run`
```

### Components
| Component | Responsibility | Design choice |
|---|---|---|
| **Source adapters** | Fetch raw data from one site or API and return records | One small interface (`fetch() -> list[Record]`); new sites plug in without touching the pipeline. This is the part reused for client work. |
| **Validation** | Parse, type-check and normalize (prices, currencies, dates) | `pydantic` models: bad data fails loudly instead of corrupting history |
| **Storage** | Append-only snapshots plus "latest state" per item | **SQLite**: zero setup, one file, versioned in the repo's data branch. Client projects can swap in PostgreSQL. |
| **Diff + rules** | Compare each run with the previous one; evaluate rules (`price_drop >= 10%`, `new_item`, `out_of_stock`, `value > X`) | Rules declared in YAML, so they're changeable without code |
| **Notifiers** | Deliver fired alerts | GitHub Issues, email (SMTP), webhook (Slack/Discord) and console; same interface, easy to add more |
| **Dashboard** | Static report generated after each run | Jinja2 + inline SVG sparklines → one HTML file. Free hosting on GitHub Pages, nothing to keep running |
| **Scheduler** | Run daily | GitHub Actions cron. Free, and its logs are public proof the system works |

### Reliability (what makes it look professional)
- Retries with exponential backoff and timeouts; rate limiting between requests
- Respects `robots.txt`; identifies itself with a clear User-Agent
- Idempotent runs: re-running the same day doesn't duplicate data
- Structured logs; each run records its status, duration and item counts
- Tests with **recorded HTML/JSON fixtures**, so they never hit the network in CI
- Lint and type checks (ruff, mypy) in CI

## 4. Stack
Python 3.12 · httpx · selectolax (fast HTML parsing) · pydantic · SQLite · Typer (CLI) · Jinja2 · pytest · ruff · mypy · GitHub Actions · GitHub Pages. **Cost: $0.**

## 5. Repo layout
```
watchtower/
├── src/watchtower/
│   ├── sources/        # base.py, books_toscrape.py, bcb_ptax.py, kraken.py
│   ├── models.py       # pydantic records
│   ├── storage.py      # SQLite repository
│   ├── rules.py        # diff + rule engine
│   ├── notifiers/      # telegram.py, webhook.py, console.py
│   ├── dashboard/      # Jinja templates
│   ├── pipeline.py     # orchestrates one run
│   └── cli.py          # `watchtower run | report | sources`
├── tests/              # unit tests + fixtures
├── config.yaml
├── .github/workflows/  # ci.yml, daily.yml
└── README.md           # architecture diagram, how to run, how to add a source
```

## 6. Milestones (~5–7 days of work)
1. Skeleton, models, books.toscrape source, SQLite storage, CLI `run` → data in the DB
2. Diff + rules + console, GitHub Issues, email and webhook notifiers
3. BCB PTAX source + threshold rule
4. Dashboard + GitHub Pages deploy
5. GitHub Actions daily run + CI, tests, README with diagram → **release**, then add to site, LinkedIn and Fiverr gig 1

## 7. Decisions (Davi, 2026-10-21)
1. **Name:** Watchtower
2. **Sources:** books.toscrape + BCB PTAX + Kraken (swapped in for CoinGecko, whose robots.txt blocks its API)
3. **Alerts:** no Telegram. Proposed: **GitHub Issues** for the live demo (GitHub emails the alert; zero secrets), plus **email (SMTP)** and **webhook** notifiers built for client use. Confirmed.
4. **Storage:** SQLite
5. **Repo:** public, `odavicoelho/watchtower`
