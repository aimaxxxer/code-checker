"""The AliExpress signature is the one thing that must be byte-exact."""

from __future__ import annotations

import hashlib
import hmac

from product_scout.providers.aliexpress import _extract_products, sign_request


def test_sha256_signature_matches_manual_hmac():
    params = {"method": "aliexpress.affiliate.product.query", "app_key": "12345", "keywords": "lamp"}
    expected = hmac.new(
        b"secret",
        b"app_key12345keywordslampmethodaliexpress.affiliate.product.query",
        hashlib.sha256,
    ).hexdigest().upper()
    assert sign_request(params, "secret", "sha256") == expected


def test_md5_signature_wraps_the_secret():
    params = {"b": "2", "a": "1"}
    expected = hashlib.md5(b"seca1b2sec").hexdigest().upper()
    assert sign_request(params, "sec", "md5") == expected


def test_parameters_are_sorted_not_insertion_ordered():
    forward = sign_request({"a": "1", "b": "2", "c": "3"}, "s")
    reverse = sign_request({"c": "3", "b": "2", "a": "1"}, "s")
    assert forward == reverse


def test_existing_sign_key_is_excluded_from_the_payload():
    without = sign_request({"a": "1"}, "s")
    with_stale = sign_request({"a": "1", "sign": "STALE"}, "s")
    assert without == with_stale


def test_none_values_are_omitted():
    assert sign_request({"a": "1", "b": None}, "s") == sign_request({"a": "1"}, "s")


def test_signature_is_uppercase_hex():
    signature = sign_request({"a": "1"}, "s")
    assert signature == signature.upper()
    assert len(signature) == 64
    int(signature, 16)


def test_extract_products_finds_deeply_nested_lists():
    payload = {
        "aliexpress_affiliate_product_query_response": {
            "resp_result": {"result": {"products": {"product": [
                {"product_id": 1, "product_title": "A"},
                {"product_id": 2, "product_title": "B"},
            ]}}}
        }
    }
    assert [p["product_title"] for p in _extract_products(payload)] == ["A", "B"]


def test_extract_products_tolerates_empty_and_malformed_payloads():
    assert _extract_products(None) == []
    assert _extract_products({"error_response": {"code": 25}}) == []
    assert _extract_products({"resp": {"result": []}}) == []
