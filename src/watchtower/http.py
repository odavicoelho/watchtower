"""A polite HTTP client: retries with backoff, per-host rate limiting and robots.txt checks."""

import logging
import time
from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

# Worth retrying: the server may succeed a moment later.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """A URL could not be fetched (after retries) or is not allowed."""


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 20.0,
        retries: int = 3,
        backoff: float = 1.0,
        delay: float = 1.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.user_agent = user_agent
        self.retries = retries
        self.backoff = backoff
        self.delay = delay
        self._sleep = sleep
        self._clock = clock
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request: dict[str, float] = {}

    def get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        if not self.allowed(url):
            raise FetchError(f"robots.txt disallows {url}")
        last_error = ""
        for attempt in range(self.retries + 1):
            if attempt:
                wait = self.backoff * 2 ** (attempt - 1)
                log.warning("retrying url=%s attempt=%d wait=%.1fs reason=%s", url, attempt, wait, last_error)
                self._sleep(wait)
            self._throttle(url)
            try:
                response = self._client.get(url, params=params)
            except httpx.TransportError as exc:
                last_error = type(exc).__name__
                continue
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
                continue
            if response.is_error:
                raise FetchError(f"HTTP {response.status_code} for {url}")
            return response
        raise FetchError(f"giving up on {url} after {self.retries + 1} attempts ({last_error})")

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        return self._robots[origin].can_fetch(self.user_agent, url)

    def _load_robots(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser()
        try:
            response = self._client.get(f"{origin}/robots.txt")
        except httpx.TransportError:
            # Unreachable robots.txt: treat as no restrictions, like most crawlers do.
            parser.parse([])
            return parser
        if response.status_code in (401, 403):
            parser.parse(["User-agent: *", "Disallow: /"])
        elif response.is_success:
            parser.parse(response.text.splitlines())
        else:
            parser.parse([])
        return parser

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            remaining = self.delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
