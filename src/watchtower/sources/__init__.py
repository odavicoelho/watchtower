"""Source adapters. Importing this package registers every built-in source."""

from watchtower.sources import books_toscrape
from watchtower.sources.base import Source, available, create, register

__all__ = ["Source", "available", "books_toscrape", "create", "register"]
