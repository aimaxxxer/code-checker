"""SerpApi provider: retail price benchmark and search-demand trend.

Supplier cost alone tells you nothing about margin. What matters is the gap
between landed cost and what the product actually sells for in your market,
which is what the shopping engines answer.
"""

from __future__ import annotations

import statistics
from typing import Any

import httpx

from ..config import Settings
from ..models import RetailBenchmark, TrendSignal
from .base import ProviderError, coerce_float

ENDPOINT = "https://serpapi.com/search.json"


class SerpApiProvider:
    name = "serpapi"

    def __init__(self, settings: Settings, cache: Any | None = None) -> None:
        self.settings = settings
        self.cache = cache

    @property
    def ready(self) -> bool:
        return self.settings.serpapi_ready

    def _get(self, params: dict[str, Any], ttl: int | None = None) -> dict[str, Any]:
        if not self.ready:
            raise ProviderError(
                "SerpApi key is not configured.",
                remedy="Set SERPAPI_KEY (serpapi.com gives 100 free searches/month).",
            )
        cache_key = None
        if self.cache is not None:
            from ..cache import make_key

            cache_key = make_key("serpapi", params)
            hit = self.cache.get(cache_key)
            if hit is not None:
                return hit

        try:
            response = httpx.get(
                ENDPOINT,
                params={**params, "api_key": self.settings.serpapi_key},
                timeout=self.settings.http_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            remedy = "Check SERPAPI_KEY and your remaining search credits." if exc.response.status_code in (401, 429) else None
            raise ProviderError(f"SerpApi returned HTTP {exc.response.status_code}.", remedy=remedy) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach SerpApi: {exc}") from exc

        if payload.get("error"):
            raise ProviderError(f"SerpApi error: {payload['error']}")

        if self.cache is not None and cache_key:
            self.cache.set(cache_key, payload, ttl)
        return payload

    def retail_benchmark(self, query: str, market: str | None = None, currency: str | None = None) -> RetailBenchmark:
        """What this product sells for at retail, and how crowded the field is."""
        market = (market or self.settings.default_market).upper()
        currency = currency or self.settings.default_currency
        payload = self._get(
            {
                "engine": "google_shopping",
                "q": query,
                "gl": market.lower(),
                "hl": "en",
                "num": 40,
            }
        )

        results = payload.get("shopping_results") or []
        prices: list[float] = []
        sellers: set[str] = set()
        for item in results:
            price = coerce_float(item.get("extracted_price") or item.get("price"))
            if price and price > 0:
                prices.append(price)
            source = item.get("source") or item.get("store")
            if source:
                sellers.add(str(source).strip().lower())

        if not prices:
            return RetailBenchmark(
                query=query,
                market=market,
                currency=currency,
                sample_size=0,
                note="No shopping results — the query may be too specific, or the item is not sold at retail under this name.",
            )

        prices.sort()
        # Trim the tails: shopping results are full of accessories and bundles.
        trimmed = prices[len(prices) // 10 : len(prices) - len(prices) // 10] or prices

        return RetailBenchmark(
            query=query,
            market=market,
            currency=currency,
            median_price=round(statistics.median(trimmed), 2),
            low_price=round(min(trimmed), 2),
            high_price=round(max(trimmed), 2),
            sample_size=len(prices),
            seller_count=len(sellers),
            sources=sorted(sellers)[:25],
            note="Prices are trimmed at both tails to drop accessories and bundles.",
        )

    def trend(self, keyword: str, geo: str | None = None, window: str = "today 12-m") -> TrendSignal:
        """Search-interest trajectory for a keyword."""
        geo = (geo or self.settings.default_market).upper()
        payload = self._get(
            {
                "engine": "google_trends",
                "q": keyword,
                "geo": geo,
                "data_type": "TIMESERIES",
                "date": window,
            }
        )

        series = ((payload.get("interest_over_time") or {}).get("timeline_data")) or []
        values: list[float] = []
        for point in series:
            entries = point.get("values") or []
            if entries:
                raw = entries[0].get("extracted_value")
                if raw is None:
                    raw = coerce_float(entries[0].get("value"))
                if raw is not None:
                    values.append(float(raw))

        if len(values) < 8:
            return TrendSignal(
                keyword=keyword,
                geo=geo,
                source="serpapi",
                sample_points=len(values),
                note="Not enough trend data to judge direction.",
            )

        window_size = max(4, len(values) // 6)
        recent = statistics.mean(values[-window_size:])
        prior = statistics.mean(values[-3 * window_size : -window_size]) if len(values) >= 4 * window_size else statistics.mean(values[:-window_size])
        slope_pct = ((recent - prior) / prior * 100) if prior > 0 else 0.0

        peak = max(values)
        latest = values[-1]

        if slope_pct > 120 and latest >= peak * 0.85:
            direction = "spike"
        elif slope_pct > 15:
            direction = "rising"
        elif slope_pct < -15:
            direction = "declining"
        else:
            direction = "flat"

        seasonality = None
        if peak > 0 and latest < peak * 0.35 and max(values[:len(values) // 2] or [0]) >= peak * 0.9:
            seasonality = "Interest peaked earlier in the window and has fallen well off that peak — check for seasonality before committing."

        return TrendSignal(
            keyword=keyword,
            geo=geo,
            slope_pct=round(slope_pct, 1),
            latest_value=round(latest, 1),
            peak_value=round(peak, 1),
            direction=direction,
            seasonality_warning=seasonality,
            sample_points=len(values),
            source="serpapi",
        )
