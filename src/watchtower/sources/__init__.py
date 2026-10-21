"""Source adapters. Importing this package registers every built-in source."""

from watchtower.sources import bcb_ptax, books_toscrape
from watchtower.sources.base import Source, available, create, register

__all__ = ["Source", "available", "bcb_ptax", "books_toscrape", "create", "register"]
