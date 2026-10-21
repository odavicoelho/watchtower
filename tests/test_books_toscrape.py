from decimal import Decimal

import httpx
import respx

from tests.conftest import fixture_text
from watchtower.http import HttpClient
from watchtower.sources.books_toscrape import START_URL, BooksToScrape, parse_listing


def test_parse_first_page() -> None:
    records, next_url = parse_listing(fixture_text("books_page1.html"), page_url=START_URL)

    assert len(records) == 20
    first = records[0]
    assert first.key == "a-light-in-the-attic_1000"
    assert first.name == "A Light in the Attic"  # full title, not the truncated link text
    assert first.value == Decimal("51.77")
    assert first.unit == "GBP"
    assert first.url == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    assert first.attributes == {"in_stock": True, "rating": 3}
    assert next_url == "https://books.toscrape.com/catalogue/page-2.html"


def test_last_page_has_no_next() -> None:
    records, next_url = parse_listing(
        fixture_text("books_page50.html"), page_url="https://books.toscrape.com/catalogue/page-50.html"
    )
    assert len(records) == 20
    assert next_url is None


def test_keys_are_unique_within_a_page() -> None:
    records, _ = parse_listing(fixture_text("books_page1.html"), page_url=START_URL)
    assert len({r.key for r in records}) == len(records)


@respx.mock
def test_fetch_follows_pagination_until_last_page(http: HttpClient) -> None:
    respx.get("https://books.toscrape.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(START_URL).mock(return_value=httpx.Response(200, text=fixture_text("books_page1.html")))
    respx.get("https://books.toscrape.com/catalogue/page-2.html").mock(
        return_value=httpx.Response(200, text=fixture_text("books_page50.html"))
    )

    records = BooksToScrape().fetch(http)

    assert len(records) == 40


@respx.mock
def test_fetch_respects_max_pages(http: HttpClient) -> None:
    respx.get("https://books.toscrape.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(START_URL).mock(return_value=httpx.Response(200, text=fixture_text("books_page1.html")))

    records = BooksToScrape(max_pages=1).fetch(http)

    assert len(records) == 20
