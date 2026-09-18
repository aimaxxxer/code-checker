from __future__ import annotations

import pytest

from product_scout.compliance import quality_flags, screen


@pytest.mark.parametrize("title", [
    "Nike Air Max Running Shoes",
    "Disney Frozen Elsa Doll",
    "AirPods Pro Wireless Earbuds Case",
    "Labubu Plush Keychain Figure",
    "Louis Vuitton Style Handbag",
])
def test_branded_items_are_blockers(title):
    assert screen(title).severity == "blocker"


@pytest.mark.parametrize("title", [
    "Replica Designer Watch",
    "1:1 Mirror Quality Bag",
    "AAA Quality Sunglasses",
])
def test_counterfeit_phrasing_is_a_blocker(title):
    flags = screen(title)
    assert flags.severity == "blocker"
    assert flags.ip_risk


def test_substring_brand_matches_do_not_false_positive():
    """'apple' must not fire on 'pineapple' — word boundaries matter."""
    assert not screen("Pineapple Shaped Silicone Ice Mould").ip_risk
    assert not screen("Snake Print Phone Grip").ip_risk


def test_regulated_categories_are_detected():
    assert screen("20000mAh Lithium Power Bank").regulatory
    assert screen("Vitamin C Slimming Capsules").regulatory
    assert screen("Baby Teether Silicone Toy").regulatory
    assert screen("USB Wall Charger 220V Adapter").regulatory


def test_medical_claims_are_flagged_independent_of_product():
    flags = screen("Clinically Proven Cream That Will Cure Acne")
    assert any("Medical claim" in item for item in flags.regulatory)


def test_multiple_regulatory_hits_escalate_to_high():
    flags = screen("Rechargeable Lithium Bluetooth Baby Thermometer with 220V Charger")
    assert len(flags.regulatory) >= 3
    assert flags.severity == "high"


def test_shipping_restrictions_are_detected():
    assert "Strong magnet" in screen("Neodymium Magnetic Phone Mount").shipping_restricted
    assert "Liquid" in screen("Rose Perfume Oil 50ml").shipping_restricted


def test_clean_product_has_no_flags():
    flags = screen("Bamboo Desk Organizer Tray")
    assert flags.severity == "none"
    assert not flags.ip_risk and not flags.regulatory


def test_quality_flags_catch_refund_risk():
    assert quality_flags(rating=3.9, review_count=500) 
    assert quality_flags(rating=4.8, review_count=5)
    assert quality_flags(rating=4.8, review_count=500, store_rating=80.0)
    assert quality_flags(rating=4.8, review_count=500, shipping_days=30)
    assert not quality_flags(rating=4.8, review_count=500, store_rating=97.0, shipping_days=9)
