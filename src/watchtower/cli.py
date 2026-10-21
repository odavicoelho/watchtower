import logging
from pathlib import Path
from typing import Annotated

import typer

from watchtower import config as config_module
from watchtower import pipeline, sources
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
    storage = Storage(cfg.database)
    http = HttpClient(
        user_agent=cfg.user_agent,
        timeout=cfg.http.timeout,
        retries=cfg.http.retries,
        backoff=cfg.http.backoff_seconds,
        delay=cfg.http.delay_seconds,
    )
    try:
        result = pipeline.run(configured, storage=storage, http=http)
    finally:
        http.close()
        storage.close()

    for r in result.sources:
        line = f"  {r.source:<20} {r.status:<7} {r.items:>5} items  {r.duration_ms / 1000:.1f}s"
        typer.echo(line + (f"  ({r.error})" if r.error else ""))
    typer.echo(f"run {result.run_id}: {result.status}")
    if result.status != "ok":
        raise typer.Exit(code=1)


@app.command("sources")
def list_sources() -> None:
    """List the available source types."""
    for name in sources.available():
        typer.echo(name)
