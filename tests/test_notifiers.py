import json

import httpx
import pytest
import respx

from watchtower import notifiers
from watchtower.notifiers import Email, GitHubIssue, Notifier, Webhook, render
from watchtower.rules import Alert

ALERTS = [
    Alert("price_drop", "shop", "b1", "Book One", "10 GBP → 8 GBP (-20.0%)", "https://shop/b1"),
    Alert("threshold", "bcb_ptax", "USD", "US dollar", "rose above 5.3 BRL: now 5.35 BRL"),
]


def test_render_groups_by_source() -> None:
    assert render(ALERTS) == (
        "[bcb_ptax]\n- US dollar: rose above 5.3 BRL: now 5.35 BRL\n\n"
        "[shop]\n- Book One: 10 GBP → 8 GBP (-20.0%) <https://shop/b1>"
    )


@respx.mock
def test_github_issue_uses_the_actions_token_and_repository() -> None:
    route = respx.post("https://api.github.com/repos/odavicoelho/watchtower/issues").mock(
        return_value=httpx.Response(201)
    )
    env = {"GITHUB_TOKEN": "t0k3n", "GITHUB_REPOSITORY": "odavicoelho/watchtower"}

    GitHubIssue(labels=["alert"], env=env).send(ALERTS, "Watchtower: 2 alerts")

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer t0k3n"
    body = json.loads(request.content)
    assert body["title"] == "Watchtower: 2 alerts"
    assert body["labels"] == ["alert"]
    assert "[Book One](https://shop/b1)" in body["body"]


@respx.mock
def test_webhook_posts_slack_and_discord_compatible_json() -> None:
    route = respx.post("https://hooks.example/abc").mock(return_value=httpx.Response(200))

    Webhook(env={"WATCHTOWER_WEBHOOK_URL": "https://hooks.example/abc"}).send(ALERTS, "Title")

    body = json.loads(route.calls.last.request.content)
    assert body["text"].startswith("*Title*")
    assert body["content"].startswith("**Title**")
    assert len(body["alerts"]) == 2


def test_missing_secrets_fail_at_startup_not_at_alert_time() -> None:
    with pytest.raises(ValueError, match="WATCHTOWER_SMTP_USER"):
        Email(to="me@example.com", env={})
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        GitHubIssue(env={})


class Broken(Notifier):
    type = "broken"

    def send(self, alerts: list[Alert], title: str) -> None:
        raise ConnectionError("down")


class Recorder(Notifier):
    type = "recorder"

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, alerts: list[Alert], title: str) -> None:
        self.sent.append(title)


def test_one_failing_channel_does_not_block_the_others() -> None:
    recorder = Recorder()

    failures = notifiers.notify([Broken(), recorder], ALERTS, "Title")

    assert recorder.sent == ["Title"]
    assert failures == ["broken: ConnectionError: down"]


@respx.mock
def test_github_issue_sends_no_labels_by_default() -> None:
    route = respx.post("https://api.github.com/repos/o/r/issues").mock(return_value=httpx.Response(201))

    GitHubIssue(env={"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}).send(ALERTS, "Title")

    assert "labels" not in json.loads(route.calls.last.request.content)
