from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# Extra per-item facts a source can attach (stock status, rating, ...). Kept flat and JSON-friendly.
Scalar = str | int | float | bool | None


class Record(BaseModel):
    """One item as seen by one source at fetch time.

    Sources only describe *what* they saw; the pipeline decides *when* it was observed.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    # Stable identifier of the item within its source (e.g. a product slug). Must not change between runs.
    key: str
    name: str
    url: str | None = None
    # The tracked number: a price, an exchange rate, a count. Decimal so money never drifts.
    value: Decimal | None = None
    unit: str | None = None
    attributes: dict[str, Scalar] = Field(default_factory=dict)
