import logging
from pathlib import Path
from typing import Annotated

import typer

from watchtower import config as config_module
from watchtower import dashboard, notifiers, pipeline, rules, sources
from watchtower.http import HttpClient
from watchtower.storage import Storage

app = typer.Typer(help="Watchtower: collect data on a schedule, keep its history, detect changes, alert.")

ConfigOption = Annotated[Path, typer.Option("--config", "-c", help="Path to config.yaml")]


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command()
def run(config: ConfigOption = Path("config.yaml")) -> None:
    """Fetch every configured source once and store the results."""
    cfg = config_module.load(config)
    configured = [sources.create(s.type, s.options) for s in cfg.sources]
    configured_rules = [rules.create(r.type, r.options) for r in cfg.rules]
    configured_notifiers = [notifiers.create(n.type, n.options) for n in cfg.notifiers]
    storage = Storage(cfg.database)
    http = HttpClient(
        user_agent=cfg.user_agent,
        timeout=cfg.http.timeout,
        retries=cfg.http.retries,
        backoff=cfg.http.backoff_seconds,
        delay=cfg.http.delay_seconds,
    )
    try:
        result = pipeline.run(
            configured, storage=storage, http=http, rules=configured_rules, notifiers=configured_notifiers
        )
    finally:
        http.close()
        storage.close()

    for r in result.sources:
        line = f"  {r.source:<20} {r.status:<7} {r.items:>5} items  {r.duration_ms / 1000:.1f}s"
        typer.echo(line + (f"  ({r.error})" if r.error else ""))
    typer.echo(f"run {result.run_id}: {result.status}, {len(result.alerts)} new alerts")
    for failure in result.notify_failures:
        typer.echo(f"  notifier failed: {failure}", err=True)
    if result.status != "ok":
        raise typer.Exit(code=1)


@app.command()
def report(
    config: ConfigOption = Path("config.yaml"),
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory")] = Path("site"),
) -> None:
    """Build the static dashboard from the database."""
    cfg = config_module.load(config)
    storage = Storage(cfg.database)
    try:
        path = dashboard.write(storage, out)
    finally:
        storage.close()
    typer.echo(f"dashboard written to {path}")


@app.command("sources")
def list_sources() -> None:
    """List the available source types."""
    for name in sources.available():
        typer.echo(name)
