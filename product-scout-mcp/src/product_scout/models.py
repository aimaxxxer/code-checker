"""Normalised data shapes shared across providers and the scoring engine.

Every provider returns `Offer` objects regardless of which marketplace or
scraper produced them, so the scoring engine never has to care about source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


@dataclass
class Offer:
    """A single supplier listing, normalised across marketplaces."""

    source: str
    product_id: str
    title: str
    url: str | None = None
    image: str | None = None
    currency: str = "USD"

    price: float | None = None
    original_price: float | None = None
    discount_pct: float | None = None
    shipping_cost: float | None = None
    shipping_days: int | None = None
    ships_from: str | None = None

    units_sold: int | None = None
    rating: float | None = None
    review_count: int | None = None
    listing_age_days: int | None = None

    store_name: str | None = None
    store_id: str | None = None
    store_rating: float | None = None
    store_years: float | None = None

    moq: int | None = None
    weight_kg: float | None = None
    category: str | None = None
    has_video: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def units_per_day(self) -> float | None:
        """Sales velocity — far more informative than a raw lifetime sold count."""
        if self.units_sold is None or not self.listing_age_days:
            return None
        return round(self.units_sold / max(self.listing_age_days, 1), 3)

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_raw:
            data.pop("raw", None)
        data["units_per_day"] = self.units_per_day
        return _clean(data)


@dataclass
class RetailBenchmark:
    """What the product actually sells for at retail in the target market."""

    query: str
    market: str
    currency: str = "USD"
    median_price: float | None = None
    low_price: float | None = None
    high_price: float | None = None
    sample_size: int = 0
    seller_count: int = 0
    sources: list[str] = field(default_factory=list)
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class TrendSignal:
    """Search-demand trajectory for a keyword."""

    keyword: str
    geo: str = "US"
    slope_pct: float | None = None          # % change, recent window vs prior window
    latest_value: float | None = None       # 0-100 relative interest
    peak_value: float | None = None
    direction: str = "unknown"              # rising | flat | declining | spike | unknown
    seasonality_warning: str | None = None
    sample_points: int = 0
    source: str = "none"
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class Economics:
    """Unit economics for one sale, landed and after fees."""

    sell_price: float
    supplier_price: float
    supplier_shipping: float = 0.0
    duty: float = 0.0
    vat: float = 0.0
    payment_fees: float = 0.0
    refund_reserve: float = 0.0
    other_costs: float = 0.0
    landed_cost: float = 0.0
    gross_profit: float = 0.0
    gross_margin_pct: float = 0.0
    breakeven_cpa: float = 0.0
    breakeven_roas: float | None = None
    target_cpa: float | None = None
    net_profit: float | None = None
    net_margin_pct: float | None = None
    currency: str = "USD"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class RiskFlags:
    """Anything that should stop you before you spend money on ads."""

    ip_risk: list[str] = field(default_factory=list)
    regulatory: list[str] = field(default_factory=list)
    shipping_restricted: list[str] = field(default_factory=list)
    quality: list[str] = field(default_factory=list)
    severity: str = "none"  # none | low | medium | high | blocker

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class ScoreBreakdown:
    """The winning-product score, with every component visible."""

    total: float
    verdict: str
    components: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    penalties: list[str] = field(default_factory=list)
    confidence: str = "low"
    missing_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
