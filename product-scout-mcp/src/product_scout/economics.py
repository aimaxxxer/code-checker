"""Unit economics for import-and-resell.

The big change since 2025 is that the US $800 de minimis exemption no longer
shelters China-direct parcels, so duty is a first-class line item here rather
than an afterthought. Rates move with policy — every result carries a note
telling the caller to confirm the live rate before committing spend.
"""

from __future__ import annotations

from .models import Economics

# Indicative import duty as a fraction of declared value, by destination market,
# for China-origin consumer goods shipped direct to the customer.
# These are STARTING POINTS for modelling, not customs advice.
DEFAULT_DUTY_RATES: dict[str, float] = {
    "US": 0.30,
    "GB": 0.00,
    "UK": 0.00,
    "EU": 0.00,
    "DE": 0.00,
    "FR": 0.00,
    "CA": 0.00,
    "AU": 0.00,
}

# Consumption tax charged on import/sale, as a fraction of the sale price.
DEFAULT_VAT_RATES: dict[str, float] = {
    "US": 0.00,   # sales tax is collected from the customer, not a cost of goods
    "GB": 0.20,
    "UK": 0.20,
    "EU": 0.21,
    "DE": 0.19,
    "FR": 0.20,
    "CA": 0.05,
    "AU": 0.10,
}

DUTY_NOTES: dict[str, str] = {
    "US": (
        "US de minimis was suspended for China/Hong Kong in May 2025 and for all "
        "origins in August 2025; the flat per-parcel fee option was withdrawn in "
        "March 2026, so duty is assessed on declared value. The default 30% here "
        "is an indicative modelling rate only — confirm the rate for your HTS code "
        "before you commit ad spend."
    ),
    "GB": (
        "UK import VAT applies from the first pound; consignments at or below £135 "
        "are generally VAT-at-point-of-sale with no customs duty. Confirm current "
        "thresholds."
    ),
    "EU": (
        "EU import VAT applies from the first euro under IOSS; customs duty "
        "generally starts above €150. Confirm current thresholds."
    ),
}


def _rate(table: dict[str, float], market: str, override: float | None) -> float:
    if override is not None:
        return max(0.0, float(override))
    return table.get(market.upper(), table.get("EU", 0.0) if len(market) == 2 else 0.0)


def unit_economics(
    sell_price: float,
    supplier_price: float,
    supplier_shipping: float = 0.0,
    market: str = "US",
    currency: str = "USD",
    duty_rate: float | None = None,
    vat_rate: float | None = None,
    payment_fee_pct: float = 0.029,
    payment_fee_fixed: float = 0.30,
    refund_rate: float = 0.03,
    other_costs: float = 0.0,
    target_cpa: float | None = None,
) -> Economics:
    """Work a single sale from supplier invoice to net profit.

    `duty_rate` and `vat_rate` are fractions (0.30 = 30%). Pass them explicitly
    to model a specific HTS code; omit them to use the indicative defaults.
    """
    if sell_price <= 0:
        raise ValueError("sell_price must be positive")
    if supplier_price < 0 or supplier_shipping < 0:
        raise ValueError("supplier costs cannot be negative")

    market_key = market.upper()
    duty_r = _rate(DEFAULT_DUTY_RATES, market_key, duty_rate)
    vat_r = _rate(DEFAULT_VAT_RATES, market_key, vat_rate)

    goods_value = supplier_price + supplier_shipping
    duty = goods_value * duty_r
    vat = sell_price * vat_r
    payment_fees = sell_price * payment_fee_pct + payment_fee_fixed
    # A refund costs you the goods you already shipped, not the sale price.
    refund_reserve = refund_rate * (goods_value + duty)

    landed_cost = goods_value + duty + vat + payment_fees + refund_reserve + other_costs
    gross_profit = sell_price - landed_cost
    gross_margin_pct = gross_profit / sell_price * 100

    breakeven_cpa = max(gross_profit, 0.0)
    breakeven_roas = (sell_price / gross_profit) if gross_profit > 0 else None

    notes: list[str] = []
    if market_key in DUTY_NOTES:
        notes.append(DUTY_NOTES[market_key])
    elif duty_r > 0:
        notes.append(f"Duty modelled at {duty_r * 100:.1f}% of goods value — confirm for your HTS code.")
    if gross_profit <= 0:
        notes.append("Negative contribution margin before a single ad dollar — this cannot be fixed with better ads.")
    elif breakeven_roas and breakeven_roas > 3.0:
        notes.append(
            f"Breakeven ROAS of {breakeven_roas:.2f}x is demanding for cold paid traffic; "
            "most stores need under 2.5x to scale."
        )

    net_profit = None
    net_margin_pct = None
    if target_cpa is not None:
        net_profit = gross_profit - target_cpa
        net_margin_pct = net_profit / sell_price * 100
        if net_profit < 0:
            notes.append(f"At a {currency} {target_cpa:.2f} CPA this sells at a loss of {abs(net_profit):.2f}/order.")

    return Economics(
        sell_price=round(sell_price, 2),
        supplier_price=round(supplier_price, 2),
        supplier_shipping=round(supplier_shipping, 2),
        duty=round(duty, 2),
        vat=round(vat, 2),
        payment_fees=round(payment_fees, 2),
        refund_reserve=round(refund_reserve, 2),
        other_costs=round(other_costs, 2),
        landed_cost=round(landed_cost, 2),
        gross_profit=round(gross_profit, 2),
        gross_margin_pct=round(gross_margin_pct, 2),
        breakeven_cpa=round(breakeven_cpa, 2),
        breakeven_roas=round(breakeven_roas, 2) if breakeven_roas else None,
        target_cpa=target_cpa,
        net_profit=round(net_profit, 2) if net_profit is not None else None,
        net_margin_pct=round(net_margin_pct, 2) if net_margin_pct is not None else None,
        currency=currency,
        notes=notes,
    )


def suggest_sell_price(
    supplier_price: float,
    supplier_shipping: float = 0.0,
    market: str = "US",
    target_gross_margin: float = 0.60,
    **kwargs,
) -> float:
    """Find the sale price that hits a target gross margin, fees and duty included.

    Solved by bisection because VAT and payment fees scale with the sale price,
    so there is no clean closed form.
    """
    if not 0 < target_gross_margin < 0.95:
        raise ValueError("target_gross_margin must be between 0 and 0.95")

    low, high = 0.01, max(supplier_price + supplier_shipping, 1.0) * 60
    for _ in range(80):
        mid = (low + high) / 2
        econ = unit_economics(
            sell_price=mid,
            supplier_price=supplier_price,
            supplier_shipping=supplier_shipping,
            market=market,
            **kwargs,
        )
        if econ.gross_margin_pct / 100 < target_gross_margin:
            low = mid
        else:
            high = mid
    return round(high, 2)
