"""MCP server: the tools Claude calls.

Every tool returns plain JSON-serialisable dicts and turns provider failures
into a structured {"error", "remedy"} rather than raising, so a missing API key
degrades one tool instead of killing the session.
"""

from __future__ import annotations

from typing import Any

# The Python SDK renamed FastMCP to MCPServer in 2.x. The decorator and run
# APIs are otherwise compatible, so support both rather than pinning users to
# whichever major version happened to be current when this was written.
try:
    from mcp.server.mcpserver import MCPServer as _Server  # mcp >= 2
except ImportError:  # pragma: no cover - exercised only on mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # mcp < 2

from . import compliance
from .config import get_settings
from .economics import DEFAULT_DUTY_RATES, suggest_sell_price, unit_economics
from .models import Offer
from .pipeline import Scout
from .providers.base import ProviderError
from .scoring import WEIGHTS, score_offer
from .shortlist import Shortlist

mcp = _Server("product-scout")

_scout: Scout | None = None
_shortlist: Shortlist | None = None


def scout() -> Scout:
    global _scout
    if _scout is None:
        _scout = Scout()
    return _scout


def shortlist() -> Shortlist:
    global _shortlist
    if _shortlist is None:
        _shortlist = Shortlist(get_settings().data_dir / "shortlist.sqlite3")
    return _shortlist


def _guard(fn, *args, **kwargs) -> Any:
    try:
        return fn(*args, **kwargs)
    except ProviderError as exc:
        return exc.to_dict()
    except ValueError as exc:
        return {"error": str(exc)}


@mcp.tool()
def provider_status() -> dict[str, Any]:
    """Show which data sources are configured and what each one covers.

    Call this first when something returns synthetic data or an error — it says
    exactly which key is missing and where to get it.
    """
    return _guard(scout().status)


@mcp.tool()
def search_supplier_catalog(
    query: str,
    marketplace: str = "aliexpress",
    limit: int = 20,
    ship_to: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> dict[str, Any]:
    """Search a wholesale marketplace for listings matching a keyword.

    marketplace: aliexpress | temu | alibaba | demo.
    Returns normalised listings (price, units sold, rating, store, shipping)
    without scoring them — use find_winning_products for a ranked shortlist.
    """
    def run() -> dict[str, Any]:
        offers, provider, reason = scout().search(
            query,
            marketplace=marketplace,
            page_size=limit,
            ship_to=ship_to,
            min_price=min_price,
            max_price=max_price,
        )
        return {
            "query": query,
            "marketplace": marketplace,
            "provider": provider,
            "provider_note": reason,
            "count": len(offers),
            "offers": [o.to_dict() for o in offers[:limit]],
        }

    return _guard(run)


@mcp.tool()
def find_winning_products(
    query: str,
    marketplace: str = "aliexpress",
    market: str = "US",
    limit: int = 8,
    candidates: int = 30,
    min_score: float = 0.0,
    target_margin: float = 0.60,
) -> dict[str, Any]:
    """Full research pipeline: search, price-benchmark, risk-screen and rank.

    This is the main tool. It pulls supplier listings, finds what the product
    sells for at retail in the target market, checks search-demand direction,
    screens for IP and regulatory problems, computes unit economics including
    import duty, and returns a ranked shortlist with every score component
    shown so you can argue with it.
    """
    return _guard(
        scout().find_winners,
        query=query,
        marketplace=marketplace,
        market=market,
        limit=limit,
        candidates=candidates,
        min_score=min_score,
        target_margin=target_margin,
    )


@mcp.tool()
def score_product(
    title: str,
    supplier_price: float,
    sell_price: float | None = None,
    market: str = "US",
    units_sold: int | None = None,
    listing_age_days: int | None = None,
    rating: float | None = None,
    review_count: int | None = None,
    store_rating: float | None = None,
    store_years: float | None = None,
    shipping_days: int | None = None,
    shipping_cost: float = 0.0,
    weight_kg: float | None = None,
    ships_from: str | None = None,
    category: str | None = None,
    has_video: bool | None = None,
    competing_offers: int | None = None,
    check_trend: bool = True,
) -> dict[str, Any]:
    """Score one product you already have numbers for.

    Works with no API keys at all — useful when you found a product yourself
    (a TikTok ad, a competitor's store, a screenshot) and want it run through
    the same scoring, economics and risk screen as a pipeline result.
    """
    def run() -> dict[str, Any]:
        offer = Offer(
            source="manual",
            product_id=f"manual-{abs(hash(title)) % 10**10}",
            title=title,
            price=supplier_price,
            shipping_cost=shipping_cost,
            shipping_days=shipping_days,
            ships_from=ships_from,
            units_sold=units_sold,
            listing_age_days=listing_age_days,
            rating=rating,
            review_count=review_count,
            store_rating=store_rating,
            store_years=store_years,
            weight_kg=weight_kg,
            category=category,
            has_video=has_video,
        )

        flags = compliance.screen(title, category)
        flags.quality = compliance.quality_flags(rating, review_count, store_rating, shipping_days)

        resolved_sell_price = sell_price
        benchmark = None
        if resolved_sell_price is None:
            benchmark = scout().benchmark(title, market)
            resolved_sell_price = benchmark.median_price or suggest_sell_price(
                supplier_price, shipping_cost, market=market
            )

        econ = unit_economics(
            sell_price=resolved_sell_price,
            supplier_price=supplier_price,
            supplier_shipping=shipping_cost,
            market=market,
        )

        trend = scout().trend(title, market) if check_trend else None
        breakdown = score_offer(
            offer,
            econ=econ,
            trend=trend,
            flags=flags,
            competing_offers=competing_offers,
            retail_seller_count=benchmark.seller_count if benchmark else None,
        )

        return {
            "offer": offer.to_dict(),
            "score": breakdown.to_dict(),
            "economics": econ.to_dict(),
            "risk": flags.to_dict(),
            "trend": trend.to_dict() if trend else None,
            "retail_benchmark": benchmark.to_dict() if benchmark else None,
            "sell_price_used": resolved_sell_price,
        }

    return _guard(run)


@mcp.tool()
def estimate_unit_economics(
    sell_price: float,
    supplier_price: float,
    supplier_shipping: float = 0.0,
    market: str = "US",
    duty_rate: float | None = None,
    vat_rate: float | None = None,
    payment_fee_pct: float = 0.029,
    payment_fee_fixed: float = 0.30,
    refund_rate: float = 0.03,
    other_costs: float = 0.0,
    target_cpa: float | None = None,
) -> dict[str, Any]:
    """Work one sale from supplier invoice to net profit.

    Includes import duty, which since the 2025 suspension of the US de minimis
    exemption is a real line item on China-direct parcels rather than zero.
    Pass duty_rate/vat_rate as fractions (0.30 = 30%) to model a specific HTS
    code; omit them for indicative defaults.
    """
    def run() -> dict[str, Any]:
        econ = unit_economics(
            sell_price=sell_price,
            supplier_price=supplier_price,
            supplier_shipping=supplier_shipping,
            market=market,
            duty_rate=duty_rate,
            vat_rate=vat_rate,
            payment_fee_pct=payment_fee_pct,
            payment_fee_fixed=payment_fee_fixed,
            refund_rate=refund_rate,
            other_costs=other_costs,
            target_cpa=target_cpa,
        )
        result = econ.to_dict()
        result["price_for_60pct_margin"] = suggest_sell_price(
            supplier_price, supplier_shipping, market=market, target_gross_margin=0.60
        )
        result["indicative_duty_rates"] = DEFAULT_DUTY_RATES
        return result

    return _guard(run)


@mcp.tool()
def benchmark_retail_price(query: str, market: str = "US") -> dict[str, Any]:
    """Find what a product actually sells for at retail, and how many sellers offer it.

    The gap between this and your landed cost is the only margin that exists.
    The marketplace's own crossed-out 'original price' is not a benchmark.
    """
    return _guard(lambda: scout().benchmark(query, market).to_dict())


@mcp.tool()
def check_demand_trend(keyword: str, geo: str = "US") -> dict[str, Any]:
    """Check search-interest direction for a keyword over the last 12 months.

    Distinguishes a sustained rise from a vertical spike — a spike is usually a
    fad whose window has already closed by the time you can stock it.
    """
    return _guard(lambda: scout().trend(keyword, geo).to_dict())


@mcp.tool()
def check_product_risk(title: str, category: str | None = None) -> dict[str, Any]:
    """Screen a product for IP, regulatory and shipping-restriction problems.

    Catches trademark and counterfeit exposure, regulated categories that need
    certification before you can legally sell, and attributes carriers refuse.
    Keyword screening is a first pass, not legal advice.
    """
    def run() -> dict[str, Any]:
        flags = compliance.screen(title, category)
        result = flags.to_dict()
        result["interpretation"] = {
            "blocker": "Do not sell. Trademark or counterfeit exposure — this ends merchant accounts.",
            "high": "Multiple compliance obligations before you can legally sell.",
            "medium": "Regulated category. Budget for certification before launch.",
            "low": "Shipping constraints only — check carrier rules and lead times.",
            "none": "No keyword-level risks found. This is not a legal clearance.",
        }.get(flags.severity, "")
        return result

    return _guard(run)


@mcp.tool()
def shortlist_add(
    product_id: str,
    source: str,
    title: str,
    url: str | None = None,
    score: float | None = None,
    verdict: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Save a product to the persistent shortlist for later review.

    The shortlist survives across sessions, so this is how a product found
    today is still there when you come back to it.
    """
    entry = {
        "offer": {"product_id": product_id, "source": source, "title": title, "url": url},
        "score": {"total": score, "verdict": verdict},
    }
    return _guard(shortlist().add, entry, note)


@mcp.tool()
def shortlist_list(limit: int = 50, min_score: float | None = None) -> dict[str, Any]:
    """List saved shortlist entries, highest scoring first.

    Use `min_score` to show only the candidates still worth acting on.
    """
    return _guard(lambda: {"entries": shortlist().list(limit=limit, min_score=min_score)})


@mcp.tool()
def shortlist_remove(product_id: str, source: str | None = None) -> dict[str, Any]:
    """Remove a product from the shortlist.

    Pass `source` as well when the same product id exists on more than one
    marketplace; without it, every matching id is removed.
    """
    return _guard(shortlist().remove, product_id, source)


@mcp.tool()
def scoring_model() -> dict[str, Any]:
    """Explain how the winning-product score is computed, so you can judge it.

    Returns the weights and the reasoning behind each component, including the
    deliberate choices that differ from naive product-research tools.
    """
    return {
        "weights": WEIGHTS,
        "components": {
            "demand": "Search-trend direction blended with observed sales velocity (units/day), not lifetime units.",
            "margin": "Gross margin against a real retail benchmark, after duty, VAT, payment fees and a refund reserve.",
            "competition": "Inverted U — zero competitors scores LOW because it usually means unproven demand, not opportunity.",
            "supplier": "Product rating, store rating, review depth and store age.",
            "logistics": "Delivery days, weight and carrier-restricted attributes; local stock is a large advantage.",
            "content": "Heuristic read of creative headroom from the title: demonstrable features and stated problems.",
        },
        "gates": {
            "blocker": "IP/counterfeit exposure caps the total at 25.",
            "high": "Three or more regulatory obligations caps the total at 55.",
            "medium": "Any regulated category caps the total at 72.",
            "negative_margin": "Losing money before ads caps the total at 20.",
        },
        "confidence": "Missing signals lower confidence and are renormalised out; they never score as zero.",
        "verdict_bands": {"strong": ">=78", "promising": ">=64", "marginal": ">=48", "pass": "<48"},
        "limits": (
            "This ranks candidates against each other on available data. It cannot see your ad "
            "creative, your audience or your fulfilment, which decide most outcomes."
        ),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
