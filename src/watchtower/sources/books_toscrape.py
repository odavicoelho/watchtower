"""books.toscrape.com: a sandbox bookstore built for scraping practice (no terms-of-service concerns)."""

import re
from decimal import Decimal
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser, LexborNode

from watchtower.http import HttpClient
from watchtower.models import Record
from watchtower.sources.base import Source, register

START_URL = "https://books.toscrape.com/catalogue/page-1.html"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
PRICE = re.compile(r"\d+(?:\.\d+)?")


@register
class BooksToScrape(Source):
    name = "books_toscrape"

    def __init__(self, max_pages: int = 50) -> None:
        self.max_pages = max_pages

    def fetch(self, http: HttpClient) -> list[Record]:
        records: list[Record] = []
        url: str | None = START_URL
        pages = 0
        while url and pages < self.max_pages:
            page_records, url = parse_listing(http.get(url).text, page_url=url)
            records.extend(page_records)
            pages += 1
        return records


def parse_listing(html: str, page_url: str) -> tuple[list[Record], str | None]:
    """Parse one catalogue page. Returns its books and the URL of the next page (None on the last one)."""
    tree = LexborHTMLParser(html)
    records = [_parse_book(pod, page_url) for pod in tree.css("article.product_pod")]
    next_link = tree.css_first("li.next > a")
    next_url = urljoin(page_url, next_link.attributes["href"] or "") if next_link else None
    return records, next_url


def _parse_book(pod: LexborNode, page_url: str) -> Record:
    link = pod.css_first("h3 > a")
    if link is None:
        raise ValueError("book card without a title link")
    href = link.attributes["href"] or ""
    # "a-light-in-the-attic_1000/index.html" → "a-light-in-the-attic_1000": stable across runs.
    key = href.split("/")[0]

    price_node = pod.css_first("p.price_color")
    price_match = PRICE.search(price_node.text()) if price_node else None

    rating_node = pod.css_first("p.star-rating")
    rating_word = (rating_node.attributes.get("class") or "").split()[-1] if rating_node else ""

    stock_node = pod.css_first("p.availability")
    in_stock = stock_node is not None and "in stock" in stock_node.text().lower()

    return Record(
        source=BooksToScrape.name,
        key=key,
        # The visible title is truncated ("A Light in the ..."); the title attribute has the full one.
        name=link.attributes.get("title") or link.text(strip=True),
        url=urljoin(page_url, href),
        value=Decimal(price_match.group()) if price_match else None,
        unit="GBP",
        attributes={"in_stock": in_stock, "rating": RATINGS.get(rating_word)},
    )
