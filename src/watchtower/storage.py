"""SQLite storage: one observation per item per day, plus a log of every run.

Re-running on the same day updates that day's observation instead of duplicating it, so runs are idempotent.
"""

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from watchtower.models import Record
from watchtower.rules import Alert

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS run_sources (
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    source      TEXT NOT NULL,
    status      TEXT NOT NULL,
    items       INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    error       TEXT,
    PRIMARY KEY (run_id, source)
);

CREATE TABLE IF NOT EXISTS observations (
    source      TEXT NOT NULL,
    key         TEXT NOT NULL,
    observed_on TEXT NOT NULL,  -- YYYY-MM-DD (UTC): the idempotency grain
    observed_at TEXT NOT NULL,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    name        TEXT NOT NULL,
    url         TEXT,
    value       TEXT,           -- Decimal as text: no float rounding
    unit        TEXT,
    attributes  TEXT NOT NULL,  -- JSON
    PRIMARY KEY (source, key, observed_on)
);

CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY,
    run_id     INTEGER NOT NULL REFERENCES runs(id),
    created_on TEXT NOT NULL,
    rule       TEXT NOT NULL,
    source     TEXT NOT NULL,
    key        TEXT NOT NULL,
    name       TEXT NOT NULL,
    message    TEXT NOT NULL,
    url        TEXT,
    UNIQUE (created_on, rule, source, key)  -- one alert per item per rule per day
);
"""


@dataclass(frozen=True)
class Observation:
    record: Record
    observed_on: str
    observed_at: str


class Storage:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)

    def start_run(self, started_at: datetime) -> int:
        with self._db:
            cursor = self._db.execute("INSERT INTO runs (started_at) VALUES (?)", (started_at.isoformat(),))
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def finish_run(self, run_id: int, finished_at: datetime, status: str) -> None:
        with self._db:
            self._db.execute(
                "UPDATE runs SET finished_at = ?, status = ? WHERE id = ?",
                (finished_at.isoformat(), status, run_id),
            )

    def record_source(
        self, run_id: int, source: str, status: str, items: int, duration_ms: int, error: str | None
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO run_sources VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, source, status, items, duration_ms, error),
            )

    def save(self, records: Iterable[Record], run_id: int, observed_at: datetime) -> int:
        rows = [
            (
                r.source,
                r.key,
                observed_at.date().isoformat(),
                observed_at.isoformat(),
                run_id,
                r.name,
                r.url,
                None if r.value is None else str(r.value),
                r.unit,
                json.dumps(r.attributes, sort_keys=True),
            )
            for r in records
        ]
        with self._db:
            self._db.executemany(
                """
                INSERT INTO observations
                    (source, key, observed_on, observed_at, run_id, name, url, value, unit, attributes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, key, observed_on) DO UPDATE SET
                    observed_at = excluded.observed_at, run_id = excluded.run_id, name = excluded.name,
                    url = excluded.url, value = excluded.value, unit = excluded.unit,
                    attributes = excluded.attributes
                """,
                rows,
            )
        return len(rows)

    def save_alerts(self, alerts: Iterable[Alert], run_id: int, created_on: str) -> list[Alert]:
        """Store alerts and return only the ones not already raised today, so reruns never alert twice."""
        fresh = []
        with self._db:
            for a in alerts:
                cursor = self._db.execute(
                    """
                    INSERT INTO alerts (run_id, created_on, rule, source, key, name, message, url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (created_on, rule, source, key) DO NOTHING
                    """,
                    (run_id, created_on, a.rule, a.source, a.key, a.name, a.message, a.url),
                )
                if cursor.rowcount == 1:
                    fresh.append(a)
        return fresh

    def alerts(self, limit: int = 100) -> list[sqlite3.Row]:
        return self._db.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def latest(self, source: str, before: str | None = None) -> dict[str, Observation]:
        """Most recent observation of every item of a source, optionally strictly before a day."""
        rows = self._db.execute(
            """
            SELECT * FROM observations o
            WHERE source = ? AND observed_on = (
                SELECT MAX(observed_on) FROM observations
                WHERE source = o.source AND key = o.key AND (? IS NULL OR observed_on < ?)
            )
            """,
            (source, before, before),
        ).fetchall()
        return {row["key"]: _to_observation(row) for row in rows}

    def history(self, source: str, key: str) -> list[Observation]:
        rows = self._db.execute(
            "SELECT * FROM observations WHERE source = ? AND key = ? ORDER BY observed_on",
            (source, key),
        ).fetchall()
        return [_to_observation(row) for row in rows]

    def runs(self, limit: int = 20) -> list[sqlite3.Row]:
        return self._db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def close(self) -> None:
        self._db.close()


def _to_observation(row: sqlite3.Row) -> Observation:
    record = Record(
        source=row["source"],
        key=row["key"],
        name=row["name"],
        url=row["url"],
        value=None if row["value"] is None else Decimal(row["value"]),
        unit=row["unit"],
        attributes=json.loads(row["attributes"]),
    )
    return Observation(record=record, observed_on=row["observed_on"], observed_at=row["observed_at"])
