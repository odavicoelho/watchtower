import httpx
import pytest
import respx

from watchtower.http import FetchError, HttpClient

URL = "https://example.com/page"
ROBOTS = "https://example.com/robots.txt"


@respx.mock
def test_retries_server_errors_with_exponential_backoff(http: HttpClient, sleeps: list[float]) -> None:
    respx.get(ROBOTS).mock(return_value=httpx.Response(404))
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, text="ok")]
    )

    assert http.get(URL).text == "ok"
    assert route.call_count == 3
    assert sleeps == [1.0, 2.0]


@respx.mock
def test_retries_network_errors(http: HttpClient) -> None:
    respx.get(ROBOTS).mock(return_value=httpx.Response(404))
    respx.get(URL).mock(side_effect=[httpx.ConnectTimeout("slow"), httpx.Response(200, text="ok")])

    assert http.get(URL).text == "ok"


@respx.mock
def test_gives_up_after_all_retries(http: HttpClient) -> None:
    respx.get(ROBOTS).mock(return_value=httpx.Response(404))
    respx.get(URL).mock(return_value=httpx.Response(500))

    with pytest.raises(FetchError, match="after 3 attempts"):
        http.get(URL)


@respx.mock
def test_client_errors_fail_immediately(http: HttpClient) -> None:
    respx.get(ROBOTS).mock(return_value=httpx.Response(404))
    route = respx.get(URL).mock(return_value=httpx.Response(404))

    with pytest.raises(FetchError, match="HTTP 404"):
        http.get(URL)
    assert route.call_count == 1


@respx.mock
def test_robots_txt_is_respected(http: HttpClient) -> None:
    respx.get(ROBOTS).mock(return_value=httpx.Response(200, text="User-agent: *\nDisallow: /page\n"))
    page = respx.get(URL)

    with pytest.raises(FetchError, match=r"robots\.txt"):
        http.get(URL)
    assert not page.called


@respx.mock
def test_robots_txt_is_fetched_once_per_site(http: HttpClient) -> None:
    robots = respx.get(ROBOTS).mock(return_value=httpx.Response(404))
    respx.get(URL).mock(return_value=httpx.Response(200))

    http.get(URL)
    http.get(URL)

    assert robots.call_count == 1


@respx.mock
def test_waits_between_requests_to_the_same_host() -> None:
    sleeps: list[float] = []
    now = iter([0.0, 0.2, 1.0]).__next__  # first request at 0s; the second is attempted at 0.2s
    client = HttpClient(user_agent="t", delay=1.0, sleep=sleeps.append, clock=now)
    respx.get(ROBOTS).mock(return_value=httpx.Response(404))
    respx.get(URL).mock(return_value=httpx.Response(200))

    client.get(URL)
    client.get(URL)

    assert sleeps == [pytest.approx(0.8)]
