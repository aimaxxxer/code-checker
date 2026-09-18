"""Apify actor runner — the practical route to Temu and Alibaba.

Neither Temu nor Alibaba.com exposes a public product-search API to ordinary
developers, so sourcing data for those two comes from scraper actors. Actor
output schemas are not standardised, so `normalise` maps a wide set of common
field aliases onto our Offer shape rather than assuming one actor's keys.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import Settings
from ..models import Offer
from .base import ProviderError, coerce_float, coerce_int, first_of

API_ROOT = "https://api.apify.com/v2"


class ApifyProvider:
    name = "apify"

    def __init__(self, settings: Settings, cache: Any | None = None) -> None:
        self.settings = settings
        self.cache = cache

    @property
    def ready(self) -> bool:
        return self.settings.apify_ready

    def actor_for(self, marketplace: str) -> str:
        mapping = {
            "temu": self.settings.apify_actor_temu,
            "alibaba": self.settings.apify_actor_alibaba,
            "aliexpress": self.settings.apify_actor_aliexpress,
        }
        actor = mapping.get(marketplace.lower())
        if not actor:
            raise ProviderError(
                f"No Apify actor configured for '{marketplace}'.",
                remedy="Set APIFY_ACTOR_TEMU / APIFY_ACTOR_ALIBABA / APIFY_ACTOR_ALIEXPRESS.",
            )
        return actor

    def run_actor(self, actor_id: str, run_input: dict[str, Any], ttl: int | None = None) -> list[dict[str, Any]]:
        """Run an actor synchronously and return its dataset items."""
        if not self.ready:
            raise ProviderError(
                "Apify token is not configured.",
                remedy="Set APIFY_TOKEN from Apify Console -> Settings -> API & Integrations.",
            )

        cache_key = None
        if self.cache is not None:
            from ..cache import make_key

            cache_key = make_key("apify", {"actor": actor_id, "input": run_input})
            hit = self.cache.get(cache_key)
            if hit is not None:
                return hit

        url = f"{API_ROOT}/acts/{actor_id.replace('/', '~')}/run-sync-get-dataset-items"
        try:
            response = httpx.post(
                url,
                params={"token": self.settings.apify_token},
                json=run_input,
                timeout=max(self.settings.http_timeout, 120.0),
            )
            response.raise_for_status()
            items = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            remedy = None
            if status == 401:
                remedy = "APIFY_TOKEN is invalid or expired."
            elif status == 404:
                remedy = f"Actor '{actor_id}' does not exist or is not shared with your account."
            elif status == 402:
                remedy = "Apify account is out of credit for this run."
            raise ProviderError(f"Apify run failed with HTTP {status}.", remedy=remedy) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach Apify: {exc}") from exc

        if not isinstance(items, list):
            items = [items] if isinstance(items, dict) else []

        if self.cache is not None and cache_key:
            self.cache.set(cache_key, items, ttl)
        return items

    def search(
        self,
        query: str,
        *,
        marketplace: str = "temu",
        page_size: int = 30,
        ship_to: str | None = None,
        currency: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        **_: Any,
    ) -> list[Offer]:
        actor = self.actor_for(marketplace)
        # Actors disagree on input keys; sending the common aliases together is
        # tolerated by every actor tested (extras are ignored) and saves the
        # caller from having to know each actor's schema.
        run_input: dict[str, Any] = {
            "search": query,
            "searchTerm": query,
            "keyword": query,
            "keywords": query,
            "query": query,
            "maxItems": page_size,
            "maxResults": page_size,
            "limit": page_size,
            "country": ship_to or self.settings.default_market,
            "currency": currency or self.settings.default_currency,
        }
        if min_price is not None:
            run_input["minPrice"] = min_price
        if max_price is not None:
            run_input["maxPrice"] = max_price

        items = self.run_actor(actor, run_input)
        offers = [self.normalise(item, marketplace) for item in items]
        return [o for o in offers if o.title]

    def normalise(self, item: dict[str, Any], marketplace: str) -> Offer:
        """Map an arbitrary actor record onto our Offer shape."""
        rating = coerce_float(first_of(item, "rating", "averageRating", "starRating", "score", "averageStar"))
        if rating is not None and rating > 5:
            rating = round(rating / 20, 2)

        store = first_of(item, "store", "seller", "shop", "storeInfo", "sellerInfo")
        store_name = store_rating = None
        if isinstance(store, dict):
            store_name = first_of(store, "name", "storeName", "sellerName", "title")
            store_rating = coerce_float(first_of(store, "rating", "score", "positiveRate"))
        elif isinstance(store, str):
            store_name = store

        return Offer(
            source=marketplace,
            product_id=str(
                first_of(item, "productId", "product_id", "id", "itemId", "goodsId", "asin") or ""
            ),
            title=str(first_of(item, "title", "name", "productTitle", "goodsName", "productName") or ""),
            url=first_of(item, "url", "link", "productUrl", "detailUrl", "productLink"),
            image=first_of(item, "image", "imageUrl", "thumbnail", "mainImage", "images"),
            currency=str(first_of(item, "currency", "currencyCode") or self.settings.default_currency),
            price=coerce_float(first_of(item, "price", "salePrice", "currentPrice", "priceValue", "minPrice")),
            original_price=coerce_float(first_of(item, "originalPrice", "listPrice", "marketPrice", "oldPrice")),
            discount_pct=coerce_float(first_of(item, "discount", "discountPercentage", "discountRate")),
            shipping_cost=coerce_float(first_of(item, "shippingCost", "shippingPrice", "deliveryCost")),
            shipping_days=coerce_int(first_of(item, "shippingDays", "deliveryDays", "estimatedDelivery")),
            ships_from=first_of(item, "shipsFrom", "shipFrom", "origin", "warehouse"),
            units_sold=coerce_int(first_of(item, "sold", "unitsSold", "sales", "salesVolume", "orders", "tradeCount")),
            rating=rating,
            review_count=coerce_int(first_of(item, "reviews", "reviewCount", "reviewsCount", "ratingCount", "comments")),
            store_name=store_name or first_of(item, "storeName", "sellerName", "shopName"),
            store_rating=store_rating or coerce_float(first_of(item, "storeRating", "sellerRating", "positiveFeedback")),
            moq=coerce_int(first_of(item, "moq", "minOrderQuantity", "minOrder")),
            category=first_of(item, "category", "categoryName", "breadcrumb"),
            has_video=bool(first_of(item, "video", "videoUrl", "hasVideo")) or None,
            raw=item,
        )
