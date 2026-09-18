"""Risk screening for sourced products.

This catches the three things that most reliably turn a "winning product" into
a dead store: someone else's intellectual property, a regulated category you
cannot legally import or advertise, and items carriers refuse to fly.

Keyword screening is a first pass, not legal advice. It is deliberately tuned
to over-flag: a false positive costs you one product, a false negative can cost
you the merchant account.
"""

from __future__ import annotations

import re

from .models import RiskFlags

# Brands whose listings are routinely counterfeit on wholesale marketplaces.
BRAND_TERMS: dict[str, str] = {
    "nike": "Nike", "adidas": "Adidas", "puma": "Puma", "jordan": "Air Jordan",
    "yeezy": "Yeezy", "supreme": "Supreme", "gucci": "Gucci", "prada": "Prada",
    "louis vuitton": "Louis Vuitton", "chanel": "Chanel", "rolex": "Rolex",
    "dior": "Dior", "balenciaga": "Balenciaga", "burberry": "Burberry",
    "disney": "Disney", "marvel": "Marvel", "pixar": "Pixar", "pokemon": "Pokemon",
    "hello kitty": "Sanrio", "sanrio": "Sanrio", "nintendo": "Nintendo",
    "lego": "LEGO", "barbie": "Mattel", "harry potter": "Warner Bros",
    "star wars": "Lucasfilm", "squid game": "Netflix", "bluey": "BBC Studios",
    "labubu": "Pop Mart", "pop mart": "Pop Mart", "sonny angel": "Dreams Inc",
    "apple": "Apple", "airpods": "Apple", "airtag": "Apple", "iphone": "Apple",
    "samsung": "Samsung", "dyson": "Dyson", "stanley cup": "Stanley",
    "owala": "Owala", "yeti": "YETI", "gopro": "GoPro", "bose": "Bose",
    "jbl": "JBL", "sony": "Sony", "playstation": "Sony", "xbox": "Microsoft",
    "nfl": "NFL", "nba": "NBA", "fifa": "FIFA", "uefa": "UEFA",
    "ferrari": "Ferrari", "lamborghini": "Lamborghini", "bmw": "BMW",
}

# Phrasing that signals a knock-off even when no brand is named.
COUNTERFEIT_TERMS = [
    "replica", "1:1", "aaa quality", "mirror quality", "og quality",
    "inspired by", "dupe", "unbranded logo", "custom logo brand",
    "same as original", "clone", "knock off", "knockoff",
]

# (pattern, label, why it matters)
REGULATED_PATTERNS: list[tuple[str, str, str]] = [
    (r"\b(lithium|li-?ion|18650|lipo|power ?bank|battery pack)\b", "Lithium battery",
     "UN38.3 test report, dangerous-goods shipping and often a ground-only restriction."),
    (r"\b(vape|e-?cig|nicotine|e-?liquid|hookah|shisha)\b", "Vaping/nicotine",
     "PACT Act registration in the US; banned outright by most ad platforms and payment processors."),
    (r"\b(cbd|thc|kratom|delta-?8|hemp oil)\b", "Controlled substance",
     "Illegal to import in many markets; instant payment-processor termination risk."),
    (r"\b(supplement|vitamin|capsule|nootropic|weight ?loss|slimming|detox tea)\b", "Ingestible",
     "FDA/EFSA registration, facility requirements and strict claim rules."),
    (r"\b(cure|treat|heal|medical grade|fda approved|clinically proven|anti-?cancer)\b", "Medical claim",
     "Health claims trigger regulatory action and ad-account bans regardless of the product."),
    (r"\b(cosmetic|serum|cream|lotion|sunscreen|skin ?whitening|lash serum)\b", "Cosmetic",
     "Ingredient restrictions, INCI labelling and (EU) a Responsible Person in-market."),
    (r"\b(toy|plush|teether|pacifier|baby|infant|toddler|nursery)\b", "Children's product",
     "CPSIA/EN71 testing, choking-hazard labelling and a certificate of conformity."),
    (r"\b(laser|laser pointer)\b", "Laser",
     "Class limits and FDA accession numbers; high-power units are seizable."),
    (r"\b(drone|uav|quadcopter)\b", "Drone",
     "Remote-ID and radio-certification requirements in most markets."),
    (r"\b(charger|adapter|power supply|mains|110v|220v|plug)\b", "Mains electrical",
     "UL/CE/UKCA certification and plug-type compliance; a common recall category."),
    (r"\b(wireless|bluetooth|wifi|rf|transmitter|gps tracker)\b", "Radio equipment",
     "FCC (US) / RED (EU) certification required for anything that transmits."),
    (r"\b(food|kitchen|cutting board|straw|tumbler|lunch ?box|water bottle)\b", "Food contact",
     "Food-contact material compliance and migration testing."),
    (r"\b(mask|glove|thermometer|blood pressure|oximeter|hearing aid|syringe)\b", "Medical device",
     "Device registration; frequently seized at the border without it."),
    (r"\b(car seat|helmet|harness|climbing|life ?jacket|airbag)\b", "Safety-critical",
     "Certified life-safety equipment — liability exposure is severe and uninsurable cheaply."),
]

SHIPPING_RESTRICTED_PATTERNS: list[tuple[str, str]] = [
    (r"\b(aerosol|spray can|pressurized|compressed gas)\b", "Aerosol/pressurised"),
    (r"\b(flammable|lighter|fuel|alcohol|acetone|solvent)\b", "Flammable"),
    (r"\b(magnet|neodymium|magnetic)\b", "Strong magnet"),
    (r"\b(knife|blade|sword|dagger|machete|taser|pepper spray|airsoft|replica gun)\b", "Weapon"),
    (r"\b(liquid|oil|gel|perfume|fragrance)\b", "Liquid"),
    (r"\b(powder|seed|plant|soil|live animal)\b", "Biosecurity"),
    (r"\b(glass|ceramic|mirror|fragile)\b", "Fragile in transit"),
]

_SEVERITY_ORDER = ["none", "low", "medium", "high", "blocker"]


def _bump(current: str, candidate: str) -> str:
    return candidate if _SEVERITY_ORDER.index(candidate) > _SEVERITY_ORDER.index(current) else current


def screen(text: str, category: str | None = None) -> RiskFlags:
    """Screen a product title/description for the risks that end stores."""
    haystack = f"{text or ''} {category or ''}".lower()
    flags = RiskFlags()
    severity = "none"

    for term, owner in BRAND_TERMS.items():
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", haystack):
            flags.ip_risk.append(f"Mentions '{term}' ({owner}) — trademark/counterfeit exposure.")
            severity = _bump(severity, "blocker")

    for term in COUNTERFEIT_TERMS:
        if term in haystack:
            flags.ip_risk.append(f"Counterfeit signal in listing copy: '{term}'.")
            severity = _bump(severity, "blocker")

    for pattern, label, why in REGULATED_PATTERNS:
        if re.search(pattern, haystack):
            flags.regulatory.append(f"{label}: {why}")
            severity = _bump(severity, "medium")

    for pattern, label in SHIPPING_RESTRICTED_PATTERNS:
        if re.search(pattern, haystack):
            flags.shipping_restricted.append(label)
            severity = _bump(severity, "low")

    # A pile of separate regulatory hits is qualitatively worse than one.
    if len(flags.regulatory) >= 3:
        severity = _bump(severity, "high")

    flags.severity = severity
    return flags


def quality_flags(
    rating: float | None,
    review_count: int | None,
    store_rating: float | None = None,
    shipping_days: int | None = None,
) -> list[str]:
    """Signals that the product itself will generate refunds and chargebacks."""
    out: list[str] = []
    if rating is not None and rating < 4.3:
        out.append(f"Product rating {rating} is below the 4.3 refund-risk threshold.")
    if review_count is not None and review_count < 30:
        out.append(f"Only {review_count} reviews — not enough evidence the item arrives intact.")
    if store_rating is not None and store_rating < 90:
        out.append(f"Store rating {store_rating}% suggests fulfilment problems.")
    if shipping_days is not None and shipping_days > 20:
        out.append(f"{shipping_days}-day delivery drives chargebacks and 'where is my order' tickets.")
    return out
