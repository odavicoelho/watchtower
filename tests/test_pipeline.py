from datetime import UTC, datetime
from decimal import Decimal

from watchtower import pipeline
from watchtower.http import HttpClient
from watchtower.models import Record
from watchtower.sources import Source
from watchtower.storage import Storage

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


class FakeSource(Source):
    name = "fake"

    def fetch(self, http: HttpClient) -> list[Record]:
        return [Record(source=self.name, key=f"k{i}", name=f"Item {i}", value=Decimal(i)) for i in range(3)]


class BrokenSource(Source):
    name = "broken"

    def fetch(self, http: HttpClient) -> list[Record]:
        raise RuntimeError("site changed its layout")


def test_successful_run_stores_everything(http: HttpClient) -> None:
    db = Storage(":memory:")

    result = pipeline.run([FakeSource()], storage=db, http=http, now=lambda: NOW)

    assert result.status == "ok"
    assert result.sources[0].items == 3
    assert len(db.latest("fake")) == 3
    assert db.runs()[0]["status"] == "ok"


def test_one_broken_source_does_not_lose_the_others(http: HttpClient) -> None:
    db = Storage(":memory:")

    result = pipeline.run([BrokenSource(), FakeSource()], storage=db, http=http, now=lambda: NOW)

    assert result.status == "partial"
    broken, fake = result.sources
    assert broken.status == "failed"
    assert broken.error == "RuntimeError: site changed its layout"
    assert fake.status == "ok"
    assert len(db.latest("fake")) == 3


def test_all_sources_failing_fails_the_run(http: HttpClient) -> None:
    db = Storage(":memory:")

    result = pipeline.run([BrokenSource()], storage=db, http=http, now=lambda: NOW)

    assert result.status == "failed"
