"""Static dashboard: a single self-contained HTML page (no JavaScript, no assets) rebuilt after each run."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import mean

from jinja2 import Environment, PackageLoader, select_autoescape

from watchtower.storage import Storage

REPO_URL = "https://github.com/odavicoelho/watchtower"
# How each source is presented. Sources not listed here still render, with a generic title.
SOURCE_INFO = {
    "bcb_ptax": ("Exchange rates", "Official daily closing rates from Banco Central do Brasil (PTAX)."),
    "kraken": ("Crypto prices", "Last traded prices from Kraken's public market data API."),
    "books_toscrape": ("Bookstore catalogue", "Prices and stock of a sandbox bookstore built for scraping."),
}


@dataclass(frozen=True)
class Tile:
    name: str
    key: str
    value: str
    unit: str
    change: float | None  # vs previous observation, percent
    sparkline: str  # SVG path, empty when there is a single point
    url: str | None


def sparkline(values: list[Decimal], width: int = 160, height: int = 40) -> str:
    """SVG path data for a small line chart; flat lines are centred."""
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    span = high - low
    step = width / (len(values) - 1)
    points = []
    for i, v in enumerate(values):
        y = height / 2 if span == 0 else height - float((v - low) / span) * height
        points.append(f"{'M' if i == 0 else 'L'}{i * step:.1f},{y:.1f}")
    return " ".join(points)


def _format(value: Decimal | None) -> str:
    if value is None:
        return "—"
    if value >= 1000:
        return f"{value:,.0f}"
    if value >= 10:
        return f"{value:,.2f}"
    return f"{value:.4f}"


def _tiles(storage: Storage, source: str, limit: int = 12) -> list[Tile]:
    tiles = []
    for key, latest in sorted(storage.latest(source).items())[:limit]:
        history = [o.record.value for o in storage.history(source, key) if o.record.value is not None]
        change = None
        if len(history) >= 2 and history[-2]:
            change = float((history[-1] - history[-2]) / history[-2] * 100)
        r = latest.record
        tiles.append(
            Tile(r.name, key, _format(r.value), r.unit or "", change, sparkline(history[-30:]), r.url)
        )
    return tiles


def _catalogue_summary(storage: Storage, source: str) -> dict[str, str | int]:
    latest = [o.record for o in storage.latest(source).values()]
    prices = [r.value for r in latest if r.value is not None]
    in_stock = sum(1 for r in latest if r.attributes.get("in_stock") is True)
    return {
        "items": len(latest),
        "in_stock": in_stock,
        "average": _format(Decimal(str(round(mean(prices), 2)))) if prices else "—",
        "unit": latest[0].unit or "" if latest else "",
    }


def build_context(storage: Storage, now: datetime | None = None) -> dict[str, object]:
    runs = storage.runs(limit=1)
    last_run = runs[0] if runs else None
    sections = []
    # Known sources in a fixed order (live data first), then any others alphabetically.
    order = list(SOURCE_INFO)
    for source in sorted(storage.sources(), key=lambda s: (order.index(s) if s in order else len(order), s)):
        title, description = SOURCE_INFO.get(source, (source, ""))
        many = len(storage.latest(source)) > 12
        sections.append(
            {
                "source": source,
                "title": title,
                "description": description,
                "summary": _catalogue_summary(storage, source) if many else None,
                "tiles": [] if many else _tiles(storage, source),
            }
        )
    return {
        "generated_at": (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC"),
        "last_run": last_run,
        "last_run_sources": storage.run_sources(last_run["id"]) if last_run else [],
        "stats": storage.stats(),
        "alerts": storage.alerts(limit=25),
        "sections": sections,
        "repo_url": REPO_URL,
    }


def render(storage: Storage, now: datetime | None = None) -> str:
    env = Environment(loader=PackageLoader("watchtower"), autoescape=select_autoescape())
    return env.get_template("dashboard.html").render(**build_context(storage, now))


def write(storage: Storage, out_dir: str | Path) -> Path:
    path = Path(out_dir) / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(storage), encoding="utf-8")
    return path
