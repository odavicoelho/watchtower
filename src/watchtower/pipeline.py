"""One run: fetch every source, store what was seen, log the outcome.

Sources are isolated: one broken site marks the run as "partial" instead of losing everyone else's data.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from watchtower.http import HttpClient
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


@dataclass
class RunResult:
    run_id: int
    status: str  # "ok" | "partial" | "failed"
    sources: list[SourceResult] = field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(UTC)


def run(
    sources: list[Source],
    *,
    storage: Storage,
    http: HttpClient,
    now: Callable[[], datetime] = utcnow,
) -> RunResult:
    started_at = now()
    run_id = storage.start_run(started_at)
    results = [_run_source(source, run_id, started_at, storage, http) for source in sources]

    failed = sum(r.status == "failed" for r in results)
    status = "ok" if failed == 0 else "failed" if failed == len(results) else "partial"
    storage.finish_run(run_id, now(), status)
    log.info("run finished run_id=%d status=%s", run_id, status)
    return RunResult(run_id=run_id, status=status, sources=results)


def _run_source(
    source: Source, run_id: int, observed_at: datetime, storage: Storage, http: HttpClient
) -> SourceResult:
    start = time.monotonic()
    try:
        records = source.fetch(http)
        items = storage.save(records, run_id, observed_at)
        result = SourceResult(source.name, "ok", items, _elapsed_ms(start))
        log.info("source ok source=%s items=%d duration_ms=%d", source.name, items, result.duration_ms)
    except Exception as exc:  # isolate any source failure from the rest of the run
        result = SourceResult(source.name, "failed", 0, _elapsed_ms(start), f"{type(exc).__name__}: {exc}")
        log.error("source failed source=%s error=%s", source.name, result.error)
    storage.record_source(
        run_id, result.source, result.status, result.items, result.duration_ms, result.error
    )
    return result


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
