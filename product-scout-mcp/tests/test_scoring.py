from __future__ import annotations

from product_scout.compliance import screen
from product_scout.economics import unit_economics
from product_scout.models import Offer, RiskFlags, TrendSignal
from product_scout.scoring import score_competition, score_offer, verdict_for


def make_offer(**kwargs) -> Offer:
    base = dict(
        source="test", product_id="1", title="Portable Rechargeable Posture Corrector",
        price=8.0, units_sold=5000, listing_age_days=200, rating=4.7, review_count=1200,
        store_rating=96.0, store_years=5.0, shipping_days=10, weight_kg=0.3,
    )
    base.update(kwargs)
    return Offer(**base)


def test_competition_is_an_inverted_u_not_monotonic():
    """Zero competitors must score below a healthy field — it means unproven demand."""
    none_at_all, _ = score_competition(0)
    healthy, _ = score_competition(12)
    saturated, _ = score_competition(300)
    assert none_at_all < healthy
    assert saturated < healthy
    assert saturated < none_at_all


def test_missing_signals_lower_confidence_rather_than_scoring_zero():
    bare = Offer(source="t", product_id="1", title="Widget", price=5.0)
    rich = make_offer()
    bare_score = score_offer(bare)
    rich_score = score_offer(rich, competing_offers=12)
    assert bare_score.confidence == "low"
    assert rich_score.confidence in ("medium", "high")
    assert "demand" not in bare_score.components
    assert "demand" in bare_score.missing_signals
    # A product with no data must not be dragged to zero by the absence.
    assert bare_score.total > 20


def test_ip_risk_caps_the_total_even_with_perfect_economics():
    offer = make_offer(title="Nike Air Jordan Replica AAA Quality Sneakers")
    flags = screen(offer.title)
    econ = unit_economics(sell_price=90.0, supplier_price=8.0, market="US")
    result = score_offer(offer, econ=econ, flags=flags, competing_offers=12)
    assert flags.severity == "blocker"
    assert result.total <= 25
    assert result.verdict == "pass"
    assert any("Capped at 25" in p for p in result.penalties)


def test_negative_margin_caps_the_total():
    offer = make_offer(price=40.0)
    econ = unit_economics(sell_price=15.0, supplier_price=40.0, market="US")
    result = score_offer(offer, econ=econ, competing_offers=12)
    assert result.total <= 20


def test_regulated_category_caps_below_strong():
    offer = make_offer(title="Rechargeable Lithium Battery Power Bank 20000mAh")
    flags = screen(offer.title)
    econ = unit_economics(sell_price=45.0, supplier_price=8.0, market="US")
    result = score_offer(offer, econ=econ, flags=flags, competing_offers=12)
    assert flags.regulatory
    assert result.total <= 72


def test_velocity_beats_lifetime_volume_for_demand():
    """Same lifetime sales, very different age — the fast mover must score higher."""
    fast = make_offer(units_sold=5000, listing_age_days=30)
    slow = make_offer(units_sold=5000, listing_age_days=1500)
    assert score_offer(fast, competing_offers=12).components["demand"] > \
           score_offer(slow, competing_offers=12).components["demand"]


def test_declining_trend_hurts_demand():
    offer = make_offer()
    rising = TrendSignal(keyword="x", slope_pct=60.0, direction="rising", sample_points=52)
    falling = TrendSignal(keyword="x", slope_pct=-50.0, direction="declining", sample_points=52)
    assert score_offer(offer, trend=rising).components["demand"] > \
           score_offer(offer, trend=falling).components["demand"]


def test_a_fad_spike_is_capped_below_a_steady_rise():
    offer = make_offer()
    spike = TrendSignal(keyword="x", slope_pct=400.0, direction="spike", sample_points=52)
    steady = TrendSignal(keyword="x", slope_pct=60.0, direction="rising", sample_points=52)
    assert score_offer(offer, trend=spike).components["demand"] <= \
           score_offer(offer, trend=steady).components["demand"]


def test_commodity_titles_lose_content_score():
    commodity = make_offer(title="Clear Silicone Phone Case Cover")
    distinctive = make_offer(title="Foldable Automatic Magnetic Cable Organizer Anti-tangle")
    assert score_offer(commodity).components["content"] < score_offer(distinctive).components["content"]


def test_local_stock_beats_china_direct_on_logistics():
    local = make_offer(ships_from="US", shipping_days=4)
    direct = make_offer(ships_from="CN", shipping_days=25)
    assert score_offer(local).components["logistics"] > score_offer(direct).components["logistics"]


def test_scores_stay_inside_bounds():
    for offer in (make_offer(), make_offer(price=0.01), make_offer(rating=1.0, store_rating=10.0)):
        result = score_offer(offer, flags=RiskFlags(), competing_offers=5)
        assert 0 <= result.total <= 100
        assert all(0 <= v <= 100 for v in result.components.values())


def test_verdict_bands():
    assert verdict_for(85) == "strong"
    assert verdict_for(70) == "promising"
    assert verdict_for(50) == "marginal"
    assert verdict_for(20) == "pass"
