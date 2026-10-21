"""One run: fetch every source, store what was seen, detect changes, notify, log the outcome.

Sources are isolated: one broken site marks the run as "partial" instead of losing everyone else's data.
"""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from watchtower import notifiers as notifiers_module
from watchtower import rules as rules_module
from watchtower.http import HttpClient
from watchtower.notifiers import Notifier
from watchtower.rules import Alert, Rule
from watchtower.sources import Source
from watchtower.storage import Storage

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceResult:
    source: str
    status: str  # "ok" | "failed"
    items: int
    duration_ms: int
    error: str | None = None
    alerts: list[Alert] = field(default_factory=list)


@dataclass
class RunResult:
    run_id: int
    status: str  # "ok" | "partial" | "failed"
    sources: list[SourceResult] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    notify_failures: list[str] = field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(UTC)


def run(
    sources: Sequence[Source],
    *,
    storage: Storage,
    http: HttpClient,
    rules: Sequence[Rule] = (),
    notifiers: Sequence[Notifier] = (),
    now: Callable[[], datetime] = utcnow,
) -> RunResult:
    started_at = now()
    run_id = storage.start_run(started_at)
    results = [_run_source(source, run_id, started_at, storage, http, list(rules)) for source in sources]

    failed = sum(r.status == "failed" for r in results)
    status = "ok" if failed == 0 else "failed" if failed == len(results) else "partial"
    alerts = [a for r in results for a in r.alerts]
    notify_failures: list[str] = []
    if alerts and notifiers:
        title = f"Watchtower: {len(alerts)} alert{'s' if len(alerts) != 1 else ''} on {started_at.date()}"
        notify_failures = notifiers_module.notify(list(notifiers), alerts, title)

    storage.finish_run(run_id, now(), status)
    log.info("run finished run_id=%d status=%s alerts=%d", run_id, status, len(alerts))
    return RunResult(run_id, status, results, alerts, notify_failures)


def _run_source(
    source: Source,
    run_id: int,
    observed_at: datetime,
    storage: Storage,
    http: HttpClient,
    rules: list[Rule],
) -> SourceResult:
    start = time.monotonic()
    today = observed_at.date().isoformat()
    try:
        records = source.fetch(http)
        items = storage.save(records, run_id, observed_at)
        previous = {key: obs.record for key, obs in storage.latest(source.name, before=today).items()}
        raised = rules_module.evaluate(rules, previous, records)
        fresh = storage.save_alerts(raised, run_id, today)
        result = SourceResult(source.name, "ok", items, _elapsed_ms(start), alerts=fresh)
        log.info(
            "source ok source=%s items=%d alerts=%d duration_ms=%d",
            source.name,
            items,
            len(fresh),
            result.duration_ms,
        )
    except Exception as exc:  # isolate any source failure from the rest of the run
        result = SourceResult(source.name, "failed", 0, _elapsed_ms(start), f"{type(exc).__name__}: {exc}")
        log.error("source failed source=%s error=%s", source.name, result.error)
    storage.record_source(
        run_id, result.source, result.status, result.items, result.duration_ms, result.error
    )
    return result


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
