from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class HttpSettings(BaseModel):
    timeout: float = 20.0
    retries: int = 3
    backoff_seconds: float = 1.0
    # Minimum pause between two requests to the same host.
    delay_seconds: float = 1.0


class SourceConfig(BaseModel):
    type: str
    options: dict[str, Any] = Field(default_factory=dict)


class Config(BaseModel):
    user_agent: str = "watchtower/0.1 (+https://github.com/odavicoelho/watchtower)"
    database: Path = Path("data/watchtower.db")
    http: HttpSettings = Field(default_factory=HttpSettings)
    sources: list[SourceConfig]


def load(path: str | Path) -> Config:
    with open(path, encoding="utf-8") as f:
        return Config.model_validate(yaml.safe_load(f))
