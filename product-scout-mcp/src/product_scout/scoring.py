"""The winning-product score.

Design notes worth knowing before you trust a number out of this file:

1. Competition is scored on an inverted U, not "less is better". Zero
   competitors usually means no proven demand, not an untapped goldmine.
   The sweet spot is a handful of sellers already making money.
2. Margin is computed from landed cost against a real retail benchmark, not
   from the marketplace's own crossed-out "original price", which is fiction.
3. Missing signals lower *confidence*, they do not silently score as zero.
   A product with no trend data is unknown, not bad.
4. Risk gates cap the total rather than subtracting from it, so a product with
   a trademark problem cannot rank highly on the strength of a fat margin.
"""

from __future__ import annotations

from .models import Economics, Offer, RiskFlags, ScoreBreakdown, TrendSignal

WEIGHTS: dict[str, float] = {
    "demand": 0.25,
    "margin": 0.25,
    "competition": 0.15,
    "supplier": 0.15,
    "logistics": 0.10,
    "content": 0.10,
}

# Title language that correlates with scroll-stopping ad creative.
WOW_TERMS = [
    "foldable", "portable", "rechargeable", "automatic", "self-", "instant",
    "magnetic", "adjustable", "multifunction", "3d", "led", "rotating",
    "waterproof", "wireless", "smart", "mini", "collapsible", "inflatable",
    "heated", "cordless", "silent", "transparent", "glow",
]
PROBLEM_TERMS = [
    "pain", "relief", "posture", "snoring", "anti-", "stop", "prevent", "fix",
    "organizer", "storage", "saver", "remover", "cleaner", "protector",
    "non-slip", "leak", "tangle", "clog", "odor", "stain", "repair", "support",
]
COMMODITY_TERMS = [
    "phone case", "screen protector", "usb cable", "charging cable", "socks",
    "t-shirt", "keychain", "sticker", "mouse pad", "lanyard", "phone holder",
]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _lerp_score(value: float, points: list[tuple[float, float]]) -> float:
    """Piecewise-linear map from a raw metric to a 0-100 score."""
    points = sorted(points)
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= value <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return points[-1][1]


def score_demand(offer: Offer, trend: TrendSignal | None) -> tuple[float | None, list[str]]:
    """Blend search-trend direction with observed sales velocity."""
    reasons: list[str] = []
    parts: list[tuple[float, float]] = []  # (score, weight)

    if trend and trend.slope_pct is not None:
        trend_score = _lerp_score(trend.slope_pct, [(-60, 0), (-20, 20), (0, 50), (25, 75), (80, 95), (200, 100)])
        if trend.direction == "spike":
            trend_score = min(trend_score, 65)
            reasons.append("Search interest is a vertical spike — usually a fad with a short window.")
        elif trend.direction == "declining":
            reasons.append(f"Search interest down {abs(trend.slope_pct):.0f}% versus the prior window.")
        elif trend.direction == "rising":
            reasons.append(f"Search interest up {trend.slope_pct:.0f}% versus the prior window.")
        parts.append((trend_score, 0.5))

    velocity = offer.units_per_day
    if velocity is not None:
        velocity_score = _lerp_score(velocity, [(0, 5), (1, 30), (5, 60), (20, 85), (100, 100)])
        reasons.append(f"Selling about {velocity:.1f} units/day at source.")
        parts.append((velocity_score, 0.35))
    elif offer.units_sold is not None:
        sold_score = _lerp_score(offer.units_sold, [(0, 5), (100, 35), (1000, 65), (10000, 90), (50000, 100)])
        reasons.append(f"{offer.units_sold:,} lifetime units sold at source (age unknown, so velocity is a guess).")
        parts.append((sold_score, 0.25))

    if offer.review_count is not None:
        review_score = _lerp_score(offer.review_count, [(0, 5), (50, 35), (500, 70), (5000, 95), (20000, 100)])
        parts.append((review_score, 0.15))

    if not parts:
        return None, ["No demand data available."]

    total_weight = sum(w for _, w in parts)
    return _clamp(sum(s * w for s, w in parts) / total_weight), reasons


def score_margin(econ: Economics | None) -> tuple[float | None, list[str]]:
    if econ is None:
        return None, ["No retail benchmark, so margin is unknown."]
    reasons: list[str] = []
    gm = econ.gross_margin_pct
    score = _lerp_score(gm, [(-20, 0), (0, 5), (20, 25), (35, 55), (50, 75), (65, 92), (80, 100)])
    reasons.append(f"Gross margin {gm:.0f}% after duty, VAT, payment fees and a refund reserve.")
    if econ.breakeven_roas:
        reasons.append(f"Breakeven ROAS {econ.breakeven_roas:.2f}x.")
        if econ.breakeven_roas > 3.5:
            score = min(score, 35)
            reasons.append("Breakeven ROAS above 3.5x is not realistically scalable on cold traffic.")
    if econ.gross_profit < 12:
        score = min(score, 45)
        reasons.append(
            f"Only {econ.currency} {econ.gross_profit:.2f} contribution per order — too thin to absorb a CPA."
        )
    return _clamp(score), reasons


def score_competition(
    competing_offers: int | None,
    retail_seller_count: int | None = None,
) -> tuple[float | None, list[str]]:
    """Inverted U: you want proven demand without a saturated field."""
    reasons: list[str] = []
    if competing_offers is None and retail_seller_count is None:
        return None, ["No competition data available."]

    signal = competing_offers if competing_offers is not None else retail_seller_count
    assert signal is not None

    score = _lerp_score(
        signal,
        [(0, 35), (2, 60), (6, 85), (15, 95), (40, 80), (80, 55), (150, 30), (400, 10)],
    )
    if signal <= 1:
        reasons.append("Almost nobody is selling this — either you are early, or there is no demand. Validate cheaply.")
    elif signal <= 15:
        reasons.append(f"{signal} competing listings — demand is proven and the field is still open.")
    elif signal <= 80:
        reasons.append(f"{signal} competing listings — you will need a real angle to differentiate.")
    else:
        reasons.append(f"{signal} competing listings — saturated; expect bid inflation and price war.")

    if retail_seller_count is not None and competing_offers is not None and retail_seller_count > 60:
        score = min(score, 55)
        reasons.append(f"{retail_seller_count} retail sellers already at the benchmark price.")
    return _clamp(score), reasons


def score_supplier(offer: Offer) -> tuple[float | None, list[str]]:
    reasons: list[str] = []
    parts: list[tuple[float, float]] = []

    if offer.rating is not None:
        parts.append((_lerp_score(offer.rating, [(3.0, 0), (4.0, 25), (4.5, 65), (4.8, 90), (5.0, 100)]), 0.35))
        reasons.append(f"Product rated {offer.rating}.")
    if offer.store_rating is not None:
        parts.append((_lerp_score(offer.store_rating, [(70, 0), (85, 30), (93, 70), (97, 95), (100, 100)]), 0.3))
        reasons.append(f"Store rating {offer.store_rating}%.")
    if offer.review_count is not None:
        parts.append((_lerp_score(offer.review_count, [(0, 10), (30, 40), (300, 75), (3000, 100)]), 0.2))
    if offer.store_years is not None:
        parts.append((_lerp_score(offer.store_years, [(0, 15), (1, 45), (3, 80), (6, 100)]), 0.15))
        reasons.append(f"Store trading {offer.store_years:.0f} years.")

    if not parts:
        return None, ["No supplier trust data available."]
    total_weight = sum(w for _, w in parts)
    return _clamp(sum(s * w for s, w in parts) / total_weight), reasons


def score_logistics(offer: Offer, flags: RiskFlags | None = None) -> tuple[float | None, list[str]]:
    reasons: list[str] = []
    parts: list[tuple[float, float]] = []

    if offer.shipping_days is not None:
        parts.append((_lerp_score(offer.shipping_days, [(3, 100), (7, 90), (12, 65), (20, 35), (35, 5)]), 0.5))
        reasons.append(f"About {offer.shipping_days} days to the customer.")
    if offer.weight_kg is not None:
        parts.append((_lerp_score(offer.weight_kg, [(0.05, 100), (0.3, 90), (1.0, 65), (3.0, 30), (8.0, 5)]), 0.3))
        reasons.append(f"{offer.weight_kg} kg shipping weight.")
    if offer.ships_from:
        local = offer.ships_from.upper() not in {"CN", "CHINA", "HK", "HONG KONG"}
        parts.append((85.0 if local else 55.0, 0.2))
        if local:
            reasons.append(f"Local stock in {offer.ships_from} — a major delivery-time advantage.")

    if flags and flags.shipping_restricted:
        penalty_score = max(20.0, 70.0 - 15 * len(flags.shipping_restricted))
        parts.append((penalty_score, 0.4))
        reasons.append("Carrier-restricted attributes: " + ", ".join(flags.shipping_restricted) + ".")

    if not parts:
        return None, ["No logistics data available."]
    total_weight = sum(w for _, w in parts)
    return _clamp(sum(s * w for s, w in parts) / total_weight), reasons


def score_content(offer: Offer) -> tuple[float, list[str]]:
    """How much creative headroom the product gives you. Heuristic by nature."""
    reasons: list[str] = []
    title = (offer.title or "").lower()
    score = 45.0

    wow_hits = [t for t in WOW_TERMS if t in title]
    if wow_hits:
        score += min(22, 7 * len(wow_hits))
        reasons.append("Demonstrable features in the title: " + ", ".join(wow_hits[:4]) + ".")

    problem_hits = [t for t in PROBLEM_TERMS if t in title]
    if problem_hits:
        score += min(20, 8 * len(problem_hits))
        reasons.append("Solves a stated problem — the easiest kind of ad to write.")

    commodity_hits = [t for t in COMMODITY_TERMS if t in title]
    if commodity_hits:
        score -= 25
        reasons.append(f"Commodity item ({commodity_hits[0]}) — competes on price alone.")

    if offer.has_video:
        score += 10
        reasons.append("Supplier video available for creative.")

    if not wow_hits and not problem_hits:
        reasons.append("No obvious visual hook in the title; the demo would have to carry the ad.")

    return _clamp(score), reasons


def verdict_for(total: float) -> str:
    if total >= 78:
        return "strong"
    if total >= 64:
        return "promising"
    if total >= 48:
        return "marginal"
    return "pass"


def score_offer(
    offer: Offer,
    econ: Economics | None = None,
    trend: TrendSignal | None = None,
    flags: RiskFlags | None = None,
    competing_offers: int | None = None,
    retail_seller_count: int | None = None,
) -> ScoreBreakdown:
    """Combine every available signal into one ranked verdict."""
    raw: dict[str, tuple[float | None, list[str]]] = {
        "demand": score_demand(offer, trend),
        "margin": score_margin(econ),
        "competition": score_competition(competing_offers, retail_seller_count),
        "supplier": score_supplier(offer),
        "logistics": score_logistics(offer, flags),
        "content": score_content(offer),
    }

    components: dict[str, float] = {}
    reasons: list[str] = []
    missing: list[str] = []
    available_weight = 0.0
    weighted_sum = 0.0

    for name, (value, notes) in raw.items():
        reasons.extend(notes)
        if value is None:
            missing.append(name)
            continue
        components[name] = round(value, 1)
        weighted_sum += value * WEIGHTS[name]
        available_weight += WEIGHTS[name]

    # Renormalise over the signals we actually have rather than punishing gaps.
    total = weighted_sum / available_weight if available_weight else 0.0

    penalties: list[str] = []
    if flags:
        if flags.severity == "blocker":
            total = min(total, 25.0)
            penalties.append("Capped at 25: intellectual-property or counterfeit exposure.")
        elif flags.severity == "high":
            total = min(total, 55.0)
            penalties.append("Capped at 55: multiple regulatory obligations before you can legally sell.")
        elif flags.severity == "medium":
            total = min(total, 72.0)
            penalties.append("Capped at 72: regulated category — budget for compliance before launch.")
        for note in flags.quality:
            total -= 3
            penalties.append(note)

    if econ is not None and econ.gross_profit <= 0:
        total = min(total, 20.0)
        penalties.append("Capped at 20: the product loses money before any advertising.")

    total = _clamp(total)

    covered = available_weight
    if covered >= 0.85 and len(missing) == 0:
        confidence = "high"
    elif covered >= 0.6:
        confidence = "medium"
    else:
        confidence = "low"

    return ScoreBreakdown(
        total=round(total, 1),
        verdict=verdict_for(total),
        components=components,
        weights=dict(WEIGHTS),
        reasons=reasons,
        penalties=penalties,
        confidence=confidence,
        missing_signals=missing,
    )
