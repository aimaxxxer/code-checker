from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..models import Offer


class ProviderError(RuntimeError):
    """A provider could not answer. Carries a human-actionable remedy."""

    def __init__(self, message: str, remedy: str | None = None) -> None:
        super().__init__(message)
        self.remedy = remedy

    def to_dict(self) -> dict[str, Any]:
        return {"error": str(self), "remedy": self.remedy}


@runtime_checkable
class SupplierProvider(Protocol):
    name: str

    @property
    def ready(self) -> bool:
        """True when the provider has the credentials it needs."""

    def search(self, query: str, **kwargs: Any) -> list[Offer]:
        """Return normalised supplier listings for a keyword query."""


def coerce_float(value: Any) -> float | None:
    """Parse the many ways marketplaces express a price. '$12.34' -> 12.34"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    cleaned = []
    for ch in text:
        if ch.isdigit() or ch in ".,":
            cleaned.append(ch)
        elif cleaned:
            break
    blob = "".join(cleaned)
    if not blob:
        return None
    # "1.234,56" (EU) vs "1,234.56" (US)
    if "," in blob and "." in blob:
        blob = blob.replace(".", "").replace(",", ".") if blob.rfind(",") > blob.rfind(".") else blob.replace(",", "")
    elif blob.count(",") == 1 and len(blob.split(",")[-1]) in (1, 2):
        blob = blob.replace(",", ".")
    else:
        blob = blob.replace(",", "")
    try:
        return float(blob)
    except ValueError:
        return None


def coerce_int(value: Any) -> int | None:
    """Parse counts including marketplace shorthand: '1.2K sold' -> 1200."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().lower()
    if not text:
        return None
    multiplier = 1
    if "k" in text:
        multiplier = 1_000
    elif "m" in text:
        multiplier = 1_000_000
    number = coerce_float(text)
    if number is None:
        return None
    return int(number * multiplier)


def first_of(data: dict[str, Any], *keys: str) -> Any:
    """Pull the first present key from a dict — scraper schemas vary wildly."""
    for key in keys:
        if key in data and data[key] not in (None, "", []):
            return data[key]
    lowered = {k.lower().replace("_", ""): v for k, v in data.items()}
    for key in keys:
        probe = key.lower().replace("_", "")
        if probe in lowered and lowered[probe] not in (None, "", []):
            return lowered[probe]
    return None
