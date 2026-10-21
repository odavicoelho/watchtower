from pathlib import Path

import pytest

from watchtower.http import HttpClient

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def sleeps() -> list[float]:
    """Records every pause the client would have taken, so tests run instantly."""
    return []


@pytest.fixture
def http(sleeps: list[float]) -> HttpClient:
    return HttpClient(user_agent="watchtower-test", retries=2, backoff=1.0, delay=0.0, sleep=sleeps.append)
