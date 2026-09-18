"""Offline fixture provider.

Lets the whole pipeline — search, benchmark, trend, score — run end to end with
no credentials at all, so you can see the shape of the output and test the
scoring engine before paying for anything. Every record is clearly synthetic.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from ..models import Offer, RetailBenchmark, TrendSignal

_CATALOG: list[dict[str, Any]] = [
    {
        "title": "Foldable Portable Neck Massager with Heat, Rechargeable Cordless",
        "price": 8.42, "original_price": 21.90, "units_sold": 14320, "listing_age_days": 210,
        "rating": 4.7, "review_count": 3104, "store_rating": 96.5, "store_years": 5.0,
        "shipping_days": 11, "weight_kg": 0.35, "category": "Health & Beauty", "has_video": True,
        "ships_from": "CN",
    },
    {
        "title": "Magnetic Cable Organizer Clips for Desk, Non-slip Cord Holder Set",
        "price": 1.18, "original_price": 3.60, "units_sold": 58200, "listing_age_days": 640,
        "rating": 4.6, "review_count": 11840, "store_rating": 94.0, "store_years": 7.0,
        "shipping_days": 14, "weight_kg": 0.05, "category": "Home Organization", "has_video": False,
        "ships_from": "CN",
    },
    {
        "title": "Automatic Pet Water Fountain 2.5L Silent Filtered Dispenser",
        "price": 12.90, "original_price": 29.99, "units_sold": 4210, "listing_age_days": 95,
        "rating": 4.8, "review_count": 890, "store_rating": 97.8, "store_years": 3.0,
        "shipping_days": 8, "weight_kg": 0.9, "category": "Pet Supplies", "has_video": True,
        "ships_from": "US",
    },
    {
        "title": "Nike Style Running Shoes Replica AAA Quality Unisex Sneakers",
        "price": 22.00, "original_price": 60.00, "units_sold": 980, "listing_age_days": 150,
        "rating": 4.4, "review_count": 320, "store_rating": 88.0, "store_years": 2.0,
        "shipping_days": 18, "weight_kg": 0.8, "category": "Shoes", "has_video": False,
        "ships_from": "CN",
    },
    {
        "title": "Rechargeable LED Posture Corrector Back Support Brace Adjustable",
        "price": 4.75, "original_price": 14.20, "units_sold": 22100, "listing_age_days": 410,
        "rating": 4.5, "review_count": 5620, "store_rating": 95.2, "store_years": 6.0,
        "shipping_days": 13, "weight_kg": 0.22, "category": "Health & Beauty", "has_video": True,
        "ships_from": "CN",
    },
    {
        "title": "Clear Silicone Phone Case Transparent Shockproof Cover",
        "price": 0.62, "original_price": 2.10, "units_sold": 96400, "listing_age_days": 900,
        "rating": 4.7, "review_count": 24800, "store_rating": 96.0, "store_years": 8.0,
        "shipping_days": 15, "weight_kg": 0.03, "category": "Phone Accessories", "has_video": False,
        "ships_from": "CN",
    },
    {
        "title": "Collapsible Silicone Travel Kettle 600ml Portable Water Boiler",
        "price": 14.30, "original_price": 32.00, "units_sold": 1860, "listing_age_days": 70,
        "rating": 4.6, "review_count": 410, "store_rating": 93.5, "store_years": 4.0,
        "shipping_days": 12, "weight_kg": 0.6, "category": "Kitchen", "has_video": True,
        "ships_from": "CN",
    },
    {
        "title": "Smart Sunrise Alarm Clock Wake Up Light with Bluetooth Speaker",
        "price": 16.80, "original_price": 44.00, "units_sold": 7350, "listing_age_days": 260,
        "rating": 4.8, "review_count": 2190, "store_rating": 98.1, "store_years": 5.0,
        "shipping_days": 10, "weight_kg": 0.55, "category": "Home", "has_video": True,
        "ships_from": "CN",
    },
]


class DemoProvider:
    """Deterministic synthetic data — same query always yields the same result."""

    name = "demo"
    ready = True

    def __init__(self, settings: Any = None, cache: Any = None) -> None:
        self.settings = settings

    def _rng(self, seed_text: str) -> random.Random:
        seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:8], 16)
        return random.Random(seed)

    def search(self, query: str, *, page_size: int = 30, marketplace: str = "demo", **_: Any) -> list[Offer]:
        rng = self._rng(query.lower())
        # Surface anything matching the query first, then fill from the catalog.
        terms = [t for t in query.lower().split() if len(t) > 2]
        ranked = sorted(
            _CATALOG,
            key=lambda row: -sum(1 for t in terms if t in row["title"].lower()),
        )
        picked = ranked[: max(1, min(page_size, len(ranked)))]

        offers: list[Offer] = []
        for index, row in enumerate(picked):
            jitter = 1 + (rng.random() - 0.5) * 0.12
            offers.append(
                Offer(
                    source=f"{marketplace}-demo",
                    product_id=f"demo-{hashlib.md5(row['title'].encode()).hexdigest()[:10]}",
                    title=row["title"],
                    url=f"https://example.invalid/demo/{index}",
                    image=None,
                    currency="USD",
                    price=round(row["price"] * jitter, 2),
                    original_price=row["original_price"],
                    discount_pct=round((1 - row["price"] / row["original_price"]) * 100, 1),
                    shipping_cost=0.0,
                    shipping_days=row["shipping_days"],
                    ships_from=row["ships_from"],
                    units_sold=row["units_sold"],
                    rating=row["rating"],
                    review_count=row["review_count"],
                    listing_age_days=row["listing_age_days"],
                    store_name=f"Demo Store {index + 1}",
                    store_rating=row["store_rating"],
                    store_years=row["store_years"],
                    weight_kg=row["weight_kg"],
                    category=row["category"],
                    has_video=row["has_video"],
                    raw={"synthetic": True},
                )
            )
        return offers

    def retail_benchmark(self, query: str, market: str = "US", currency: str = "USD", **_: Any) -> RetailBenchmark:
        rng = self._rng(f"bench:{query.lower()}")
        base = rng.uniform(19, 65)
        return RetailBenchmark(
            query=query,
            market=market,
            currency=currency,
            median_price=round(base, 2),
            low_price=round(base * 0.7, 2),
            high_price=round(base * 1.6, 2),
            sample_size=rng.randint(12, 40),
            seller_count=rng.randint(3, 70),
            sources=["demo-retailer-a", "demo-retailer-b"],
            note="SYNTHETIC demo data — not a real retail benchmark.",
        )

    def trend(self, keyword: str, geo: str = "US", **_: Any) -> TrendSignal:
        rng = self._rng(f"trend:{keyword.lower()}")
        slope = rng.uniform(-45, 90)
        direction = "rising" if slope > 15 else "declining" if slope < -15 else "flat"
        return TrendSignal(
            keyword=keyword,
            geo=geo,
            slope_pct=round(slope, 1),
            latest_value=round(rng.uniform(30, 95), 1),
            peak_value=100.0,
            direction=direction,
            sample_points=52,
            source="demo",
            note="SYNTHETIC demo data — not a real trend.",
        )
