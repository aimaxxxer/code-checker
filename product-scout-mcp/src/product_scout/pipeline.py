"""Orchestration: turn a keyword into a ranked, risk-screened shortlist.

Kept separate from the MCP layer so the whole thing is testable without a
protocol client attached.
"""

from __future__ import annotations

import re
from typing import Any

from . import compliance, scoring
from .cache import Cache
from .config import Settings, get_settings
from .economics import suggest_sell_price, unit_economics
from .models import Offer, RetailBenchmark, TrendSignal
from .providers.aliexpress import AliExpressClient
from .providers.apify import ApifyProvider
from .providers.base import ProviderError
from .providers.demo import DemoProvider
from .providers.serpapi import SerpApiProvider

MARKETPLACES = {"aliexpress", "temu", "alibaba", "demo"}

# A retail benchmark is looked up once per query, but a search returns many
# products and only some of them are actually the thing you searched for.
# Applying one median price to all of them invents margin out of nothing — a
# $0.62 phone case is not worth the $21 median of a "neck massager" search.
_STOPWORDS = {"the", "and", "for", "with", "set", "new", "pcs", "pack"}
RELEVANCE_THRESHOLD = 0.5
# Above this ratio the benchmark is almost certainly for a different product.
IMPLAUSIBLE_MARKUP = 25.0


def relevance(title: str, query: str) -> float:
    """Fraction of the query's meaningful words present in the listing title."""
    terms = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2 and t not in _STOPWORDS}
    if not terms:
        return 1.0
    title_terms = set(re.findall(r"[a-z0-9]+", (title or "").lower()))
    return len(terms & title_terms) / len(terms)


class Scout:
    """Wires providers together and runs the research pipeline."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = Cache(self.settings.data_dir / "cache.sqlite3", self.settings.cache_ttl_seconds)
        self.aliexpress = AliExpressClient(self.settings, self.cache)
        self.apify = ApifyProvider(self.settings, self.cache)
        self.serpapi = SerpApiProvider(self.settings, self.cache)
        self.demo = DemoProvider(self.settings, self.cache)

    # ---------- provider selection ----------

    def resolve_source(self, marketplace: str) -> tuple[str, str]:
        """Pick the best available provider for a marketplace.

        Returns (provider_name, reason).
        """
        marketplace = (marketplace or "aliexpress").lower()
        if marketplace == "demo":
            return "demo", "Demo mode requested."
        if marketplace == "aliexpress":
            if self.aliexpress.ready:
                return "aliexpress", "Using the official AliExpress Open Platform API."
            if self.apify.ready:
                return "apify", "No AliExpress API credentials; falling back to an Apify scraper."
            return "demo", "No credentials configured for any live source — returning synthetic demo data."
        if marketplace in {"temu", "alibaba"}:
            if self.apify.ready:
                return "apify", f"{marketplace.title()} has no public product API; using an Apify scraper."
            return "demo", (
                f"{marketplace.title()} has no public product API and APIFY_TOKEN is not set — "
                "returning synthetic demo data."
            )
        raise ProviderError(
            f"Unknown marketplace '{marketplace}'.",
            remedy=f"Choose one of: {', '.join(sorted(MARKETPLACES))}.",
        )

    def status(self) -> dict[str, Any]:
        s = self.settings
        return {
            "providers": {
                "aliexpress_official": {
                    "configured": s.aliexpress_ready,
                    "gateway": s.ae_gateway,
                    "sign_method": s.ae_sign_method,
                    "timestamp_style": s.ae_timestamp_style,
                    "covers": ["aliexpress"],
                    "setup": "portals.aliexpress.com -> join affiliate programme -> create app -> ALIEXPRESS_APP_KEY / ALIEXPRESS_APP_SECRET",
                },
                "apify": {
                    "configured": s.apify_ready,
                    "covers": ["temu", "alibaba", "aliexpress"],
                    "actors": {
                        "aliexpress": s.apify_actor_aliexpress,
                        "temu": s.apify_actor_temu,
                        "alibaba": s.apify_actor_alibaba,
                    },
                    "setup": "console.apify.com -> Settings -> API & Integrations -> APIFY_TOKEN",
                },
                "serpapi": {
                    "configured": s.serpapi_ready,
                    "covers": ["retail price benchmark", "google trends"],
                    "setup": "serpapi.com -> SERPAPI_KEY (100 free searches/month)",
                },
                "demo": {"configured": True, "covers": ["synthetic fallback for all of the above"]},
            },
            "defaults": {
                "market": s.default_market,
                "currency": s.default_currency,
                "cache_ttl_seconds": s.cache_ttl_seconds,
                "data_dir": str(s.data_dir),
            },
            "live_data_available": s.aliexpress_ready or s.apify_ready,
            "benchmark_available": s.serpapi_ready,
        }

    # ---------- primitives ----------

    def search(self, query: str, marketplace: str = "aliexpress", **kwargs: Any) -> tuple[list[Offer], str, str]:
        provider_name, reason = self.resolve_source(marketplace)
        if provider_name == "aliexpress":
            offers = self.aliexpress.search(query, **kwargs)
        elif provider_name == "apify":
            offers = self.apify.search(query, marketplace=marketplace, **kwargs)
        else:
            offers = self.demo.search(query, marketplace=marketplace, **kwargs)
        return offers, provider_name, reason

    def benchmark(self, query: str, market: str | None = None, currency: str | None = None) -> RetailBenchmark:
        if self.serpapi.ready:
            return self.serpapi.retail_benchmark(query, market, currency)
        bench = self.demo.retail_benchmark(
            query, market or self.settings.default_market, currency or self.settings.default_currency
        )
        bench.note = "SYNTHETIC — set SERPAPI_KEY for a real retail benchmark. " + (bench.note or "")
        return bench

    def trend(self, keyword: str, geo: str | None = None) -> TrendSignal:
        if self.serpapi.ready:
            return self.serpapi.trend(keyword, geo)
        signal = self.demo.trend(keyword, geo or self.settings.default_market)
        signal.note = "SYNTHETIC — set SERPAPI_KEY for real Google Trends data. " + (signal.note or "")
        return signal

    # ---------- the pipeline ----------

    def find_winners(
        self,
        query: str,
        marketplace: str = "aliexpress",
        market: str | None = None,
        limit: int = 8,
        candidates: int = 30,
        target_margin: float = 0.60,
        min_score: float = 0.0,
        include_trend: bool = True,
        **search_kwargs: Any,
    ) -> dict[str, Any]:
        """Search, benchmark, screen and rank in one pass."""
        market = (market or self.settings.default_market).upper()
        currency = self.settings.default_currency

        offers, provider_name, reason = self.search(
            query, marketplace=marketplace, page_size=candidates, ship_to=market, **search_kwargs
        )
        if not offers:
            return {
                "query": query,
                "marketplace": marketplace,
                "provider": provider_name,
                "provider_note": reason,
                "results": [],
                "note": "No listings came back. Try a broader keyword or a different marketplace.",
            }

        benchmark = self.benchmark(query, market, currency)
        trend_signal = self.trend(query, market) if include_trend else None

        # A retail benchmark is per-query, not per-listing, so it is computed
        # once and reused — the alternative is one paid lookup per candidate.
        retail_price = benchmark.median_price

        scored: list[dict[str, Any]] = []
        for offer in offers:
            flags = compliance.screen(offer.title, offer.category)
            flags.quality = compliance.quality_flags(
                offer.rating, offer.review_count, offer.store_rating, offer.shipping_days
            )

            match = relevance(offer.title, query)
            econ = None
            sell_price = None
            pricing_basis = "none"
            pricing_note = None

            if offer.price is not None:
                use_benchmark = retail_price is not None and match >= RELEVANCE_THRESHOLD
                if use_benchmark and retail_price / max(offer.price, 0.01) > IMPLAUSIBLE_MARKUP:
                    use_benchmark = False
                    pricing_note = (
                        f"Retail median {currency} {retail_price:.2f} is over {IMPLAUSIBLE_MARKUP:.0f}x the "
                        "supplier price, so it is probably benchmarking a different product. "
                        "Priced by target markup instead."
                    )

                if use_benchmark:
                    sell_price = retail_price
                    pricing_basis = "retail_benchmark"
                else:
                    sell_price = suggest_sell_price(
                        offer.price, offer.shipping_cost or 0.0, market=market, target_gross_margin=target_margin
                    )
                    pricing_basis = "target_markup"
                    if pricing_note is None:
                        pricing_note = (
                            f"Listing matches only {match:.0%} of the query, so the retail benchmark was not "
                            f"applied. Priced to hit a {target_margin:.0%} target margin — margin here is an "
                            "assumption, not a measurement."
                        )

                econ = unit_economics(
                    sell_price=sell_price,
                    supplier_price=offer.price,
                    supplier_shipping=offer.shipping_cost or 0.0,
                    market=market,
                    currency=currency,
                )

            breakdown = scoring.score_offer(
                offer,
                econ=econ,
                trend=trend_signal,
                flags=flags,
                competing_offers=len(offers),
                retail_seller_count=benchmark.seller_count or None,
            )

            if breakdown.total < min_score:
                continue

            # Margin computed from an assumed markup is circular — it measures the
            # assumption, not the product — so it must not inflate the score.
            if pricing_basis == "target_markup" and "margin" in breakdown.components:
                breakdown.components["margin"] = min(breakdown.components["margin"], 55.0)
                breakdown.confidence = "low" if breakdown.confidence == "high" else breakdown.confidence
                breakdown.reasons.append(
                    "Margin is based on a target markup, not a matched retail price — treat it as unverified."
                )

            scored.append(
                {
                    "offer": offer.to_dict(),
                    "score": breakdown.to_dict(),
                    "economics": econ.to_dict() if econ else None,
                    "risk": flags.to_dict(),
                    "suggested_sell_price": round(sell_price, 2) if sell_price else None,
                    "pricing_basis": pricing_basis,
                    "pricing_note": pricing_note,
                    "query_relevance": round(match, 2),
                }
            )

        # Rank, do not just score. A listing that does not match what you searched
        # for has unverified economics, so it must not outrank the listings that
        # were actually priced against a real retail benchmark. The displayed
        # score is left untouched; only the ordering is discounted, and the
        # discount is reported so the ordering can be argued with.
        for row in scored:
            discount = 1.0
            if row["pricing_basis"] != "retail_benchmark":
                discount = 0.6 + 0.4 * row["query_relevance"]
            row["rank_score"] = round(row["score"]["total"] * discount, 1)
            row["rank_discount"] = round(discount, 2)

        scored.sort(key=lambda row: (row["rank_score"], row["query_relevance"]), reverse=True)

        return {
            "query": query,
            "marketplace": marketplace,
            "market": market,
            "provider": provider_name,
            "provider_note": reason,
            "retail_benchmark": benchmark.to_dict(),
            "trend": trend_signal.to_dict() if trend_signal else None,
            "candidates_screened": len(offers),
            "results": scored[:limit],
            "scoring_weights": scoring.WEIGHTS,
            "ranking": (
                "Ordered by rank_score, which is the score discounted when a listing does not "
                "match the query closely enough to price against the retail benchmark. "
                "'score.total' is the undiscounted figure."
            ),
            "caveat": (
                "Scores rank candidates against each other on available data; they are not a "
                "prediction of sales. Validate the top one or two with a small test budget."
            ),
        }
