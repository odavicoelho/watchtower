"""Alert delivery. Secrets (tokens, passwords) come from environment variables, never from config files."""

import logging
import os
import smtplib
from abc import ABC, abstractmethod
from collections.abc import Mapping
from email.message import EmailMessage
from typing import Any, ClassVar

import httpx

from watchtower.rules import Alert

log = logging.getLogger(__name__)


class Notifier(ABC):
    type: ClassVar[str]

    @abstractmethod
    def send(self, alerts: list[Alert], title: str) -> None: ...


def render(alerts: list[Alert]) -> str:
    """Plain-text alert list, grouped by source. Shared by every notifier."""
    lines: list[str] = []
    for source in sorted({a.source for a in alerts}):
        lines.append(f"[{source}]")
        for a in (a for a in alerts if a.source == source):
            link = f" <{a.url}>" if a.url else ""
            lines.append(f"- {a.name}: {a.message}{link}")
        lines.append("")
    return "\n".join(lines).strip()


class Console(Notifier):
    type = "console"

    def send(self, alerts: list[Alert], title: str) -> None:
        print(f"{title}\n{render(alerts)}")


class Webhook(Notifier):
    """POSTs JSON to a URL. The `text` field makes it work with Slack and Discord-style incoming webhooks."""

    type = "webhook"

    def __init__(self, url_env: str = "WATCHTOWER_WEBHOOK_URL", env: Mapping[str, str] = os.environ) -> None:
        self.url = _required(env, url_env)

    def send(self, alerts: list[Alert], title: str) -> None:
        payload = {
            "text": f"*{title}*\n{render(alerts)}",
            "content": f"**{title}**\n{render(alerts)}"[:2000],  # Discord
            "alerts": [a.__dict__ for a in alerts],
        }
        httpx.post(self.url, json=payload, timeout=15).raise_for_status()


class Email(Notifier):
    """Sends one email per run over SMTP (STARTTLS). Works with Gmail using an app password."""

    type = "email"

    def __init__(self, to: str, env: Mapping[str, str] = os.environ) -> None:
        self.to = to
        self.host = env.get("WATCHTOWER_SMTP_HOST", "smtp.gmail.com")
        self.port = int(env.get("WATCHTOWER_SMTP_PORT", "587"))
        self.user = _required(env, "WATCHTOWER_SMTP_USER")
        self.password = _required(env, "WATCHTOWER_SMTP_PASSWORD")

    def send(self, alerts: list[Alert], title: str) -> None:
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = self.user
        message["To"] = self.to
        message.set_content(render(alerts))
        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(self.user, self.password)
            smtp.send_message(message)


class GitHubIssue(Notifier):
    """Opens one issue per run. GitHub then emails everyone watching the repo.

    Inside GitHub Actions the built-in GITHUB_TOKEN and GITHUB_REPOSITORY are all it needs: no extra secrets.
    """

    type = "github_issue"
    API = "https://api.github.com"

    def __init__(self, labels: list[str] | None = None, env: Mapping[str, str] = os.environ) -> None:
        self.token = _required(env, "GITHUB_TOKEN")
        self.repository = _required(env, "GITHUB_REPOSITORY")
        self.labels = labels or ["alert"]

    def send(self, alerts: list[Alert], title: str) -> None:
        response = httpx.post(
            f"{self.API}/repos/{self.repository}/issues",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"},
            json={"title": title, "body": _markdown(alerts), "labels": self.labels},
            timeout=15,
        )
        response.raise_for_status()


def _markdown(alerts: list[Alert]) -> str:
    rows = ["| Source | Item | What happened |", "|---|---|---|"]
    for a in alerts:
        item = f"[{a.name}]({a.url})" if a.url else a.name
        rows.append(f"| {a.source} | {item.replace('|', '/')} | {a.message} |")
    return "\n".join(rows)


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise ValueError(f"environment variable {name} is not set")
    return value


NOTIFIERS: dict[str, type[Notifier]] = {n.type: n for n in (Console, Webhook, Email, GitHubIssue)}


def create(type_name: str, options: dict[str, Any]) -> Notifier:
    try:
        cls = NOTIFIERS[type_name]
    except KeyError:
        raise ValueError(
            f"unknown notifier {type_name!r}; available: {', '.join(sorted(NOTIFIERS))}"
        ) from None
    return cls(**options)


def notify(notifiers: list[Notifier], alerts: list[Alert], title: str) -> list[str]:
    """Deliver through every notifier; one failing channel never blocks the others. Returns failures."""
    failures = []
    for notifier in notifiers:
        try:
            notifier.send(alerts, title)
        except Exception as exc:
            failures.append(f"{notifier.type}: {type(exc).__name__}: {exc}")
            log.error("notifier failed notifier=%s error=%s", notifier.type, exc)
    return failures
