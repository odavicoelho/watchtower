from abc import ABC, abstractmethod
from typing import Any, ClassVar

from watchtower.http import HttpClient
from watchtower.models import Record


class Source(ABC):
    """Fetches the current state of one website or API.

    A source knows how to read one place and nothing else: no storage, no rules, no alerts.
    Adding a new site means adding one subclass and registering it.
    """

    name: ClassVar[str]

    @abstractmethod
    def fetch(self, http: HttpClient) -> list[Record]: ...


_REGISTRY: dict[str, type[Source]] = {}


def register(cls: type[Source]) -> type[Source]:
    _REGISTRY[cls.name] = cls
    return cls


def available() -> list[str]:
    return sorted(_REGISTRY)


def create(type_name: str, options: dict[str, Any]) -> Source:
    try:
        cls = _REGISTRY[type_name]
    except KeyError:
        raise ValueError(f"unknown source type {type_name!r}; available: {', '.join(available())}") from None
    return cls(**options)
