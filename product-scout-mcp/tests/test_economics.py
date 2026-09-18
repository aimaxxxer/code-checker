from __future__ import annotations

import pytest

from product_scout.economics import suggest_sell_price, unit_economics


def test_landed_cost_accounts_for_every_line_item():
    econ = unit_economics(sell_price=40.0, supplier_price=10.0, supplier_shipping=2.0, market="US")
    assert econ.duty == pytest.approx(3.6, abs=0.01)   # 30% of 12.00 goods value
    assert econ.payment_fees == pytest.approx(40 * 0.029 + 0.30, abs=0.01)
    assert econ.landed_cost > 12.0
    total = (econ.supplier_price + econ.supplier_shipping + econ.duty + econ.vat
             + econ.payment_fees + econ.refund_reserve + econ.other_costs)
    assert econ.landed_cost == pytest.approx(total, abs=0.02)


def test_duty_is_charged_on_goods_not_on_sale_price():
    cheap = unit_economics(sell_price=40.0, supplier_price=5.0, market="US")
    dear = unit_economics(sell_price=40.0, supplier_price=20.0, market="US")
    assert dear.duty > cheap.duty


def test_breakeven_roas_is_price_over_contribution():
    econ = unit_economics(sell_price=50.0, supplier_price=10.0, market="US")
    assert econ.breakeven_roas == pytest.approx(50.0 / econ.gross_profit, abs=0.01)
    assert econ.breakeven_cpa == pytest.approx(econ.gross_profit, abs=0.01)


def test_negative_margin_is_reported_not_hidden():
    econ = unit_economics(sell_price=9.0, supplier_price=20.0, market="US")
    assert econ.gross_profit < 0
    assert econ.breakeven_roas is None
    assert any("cannot be fixed with better ads" in note for note in econ.notes)


def test_vat_market_costs_more_than_a_no_vat_market():
    us = unit_economics(sell_price=40.0, supplier_price=10.0, market="US", duty_rate=0.0)
    uk = unit_economics(sell_price=40.0, supplier_price=10.0, market="GB")
    assert uk.vat > 0 and us.vat == 0
    assert uk.landed_cost > us.landed_cost


def test_explicit_rates_override_the_defaults():
    econ = unit_economics(sell_price=40.0, supplier_price=10.0, market="US", duty_rate=0.0, vat_rate=0.0)
    assert econ.duty == 0 and econ.vat == 0


def test_target_cpa_produces_net_profit():
    econ = unit_economics(sell_price=50.0, supplier_price=10.0, market="US", target_cpa=15.0)
    assert econ.net_profit == pytest.approx(econ.gross_profit - 15.0, abs=0.01)


def test_suggested_price_actually_hits_the_target_margin():
    for target in (0.4, 0.6, 0.75):
        price = suggest_sell_price(9.0, 1.5, market="US", target_gross_margin=target)
        econ = unit_economics(sell_price=price, supplier_price=9.0, supplier_shipping=1.5, market="US")
        assert econ.gross_margin_pct / 100 == pytest.approx(target, abs=0.01)


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        unit_economics(sell_price=0, supplier_price=5)
    with pytest.raises(ValueError):
        unit_economics(sell_price=10, supplier_price=-1)
    with pytest.raises(ValueError):
        suggest_sell_price(5.0, target_gross_margin=1.5)
