"""AliExpress Open Platform client (official API).

Covers both product surfaces that matter for sourcing research:

  * Affiliate API  — aliexpress.affiliate.*  (needs an approved affiliate account)
  * Dropshipping API — aliexpress.ds.*       (needs a dropshipping-centre account)

Request signing follows the Taobao/Alibaba "TOP" scheme used by the
api-sg.aliexpress.com gateway: sort every parameter by key, concatenate
key+value with no separators, then hash. Two hash modes exist in the wild and
both are implemented, because which one a given app key accepts depends on when
and how the app was provisioned.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..config import Settings
from ..models import Offer
from .base import ProviderError, coerce_float, coerce_int, first_of

GMT8 = timezone(timedelta(hours=8))


def sign_request(params: dict[str, Any], app_secret: str, sign_method: str = "sha256") -> str:
    """Compute the TOP signature for a set of request parameters.

    sha256 -> HMAC-SHA256(secret, sorted_concat), uppercase hex
    md5    -> MD5(secret + sorted_concat + secret), uppercase hex
    """
    payload = "".join(
        f"{key}{value}"
        for key, value in sorted(params.items())
        if key != "sign" and value is not None
    )
    if sign_method.lower() == "md5":
        digest = hashlib.md5(f"{app_secret}{payload}{app_secret}".encode("utf-8")).hexdigest()
    else:
        digest = hmac.new(
            app_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    return digest.upper()


def _timestamp(style: str) -> str:
    if style == "datetime":
        # Legacy gateways expect wall-clock time in GMT+8.
        return datetime.now(GMT8).strftime("%Y-%m-%d %H:%M:%S")
    return str(int(time.time() * 1000))


class AliExpressClient:
    """Thin, signed client over the AliExpress Open Platform system gateway."""

    name = "aliexpress"

    def __init__(self, settings: Settings, cache: Any | None = None) -> None:
        self.settings = settings
        self.cache = cache

    @property
    def ready(self) -> bool:
        return self.settings.aliexpress_ready

    def _require_credentials(self) -> tuple[str, str]:
        if not self.settings.aliexpress_ready:
            raise ProviderError(
                "AliExpress Open Platform credentials are not configured.",
                remedy=(
                    "Set ALIEXPRESS_APP_KEY and ALIEXPRESS_APP_SECRET. Get them by joining "
                    "the AliExpress affiliate programme at portals.aliexpress.com, then "
                    "creating an app in the console at openservice.aliexpress.com."
                ),
            )
        assert self.settings.ae_app_key and self.settings.ae_app_secret
        return self.settings.ae_app_key, self.settings.ae_app_secret

    def call(self, method: str, params: dict[str, Any] | None = None, ttl: int | None = None) -> dict[str, Any]:
        """Invoke one Open Platform method and return the decoded payload."""
        app_key, app_secret = self._require_credentials()

        request: dict[str, Any] = {
            "method": method,
            "app_key": app_key,
            "timestamp": _timestamp(self.settings.ae_timestamp_style),
            "sign_method": self.settings.ae_sign_method,
            "format": "json",
            "v": "2.0",
            "simplify": "true",
        }
        for key, value in (params or {}).items():
            if value is None:
                continue
            request[key] = ",".join(str(v) for v in value) if isinstance(value, (list, tuple)) else str(value)

        cache_key = None
        if self.cache is not None:
            from ..cache import make_key

            cacheable = {k: v for k, v in request.items() if k not in {"timestamp", "sign"}}
            cache_key = make_key("aliexpress", cacheable)
            hit = self.cache.get(cache_key)
            if hit is not None:
                return hit

        request["sign"] = sign_request(request, app_secret, self.settings.ae_sign_method)

        try:
            response = httpx.post(
                self.settings.ae_gateway,
                data=request,
                timeout=self.settings.http_timeout,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"AliExpress gateway returned HTTP {exc.response.status_code} for {method}.",
                remedy="Check that your app key is approved for this API family.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach the AliExpress gateway: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError("AliExpress returned a non-JSON response.") from exc

        if isinstance(payload, dict):
            err = payload.get("error_response") or payload.get("error_resp")
            if err:
                code = err.get("code") or err.get("sub_code")
                message = err.get("msg") or err.get("sub_msg") or "unknown error"
                remedy = None
                if str(code) in {"25", "26", "27", "API_SIGNATURE_ERROR"} or "sign" in str(message).lower():
                    remedy = (
                        "Signature rejected. Try flipping ALIEXPRESS_SIGN_METHOD between "
                        "'sha256' and 'md5', and ALIEXPRESS_TIMESTAMP_STYLE between 'ms' "
                        "and 'datetime' — provisioning era decides which pair your app key wants."
                    )
                elif "permission" in str(message).lower() or "not authorized" in str(message).lower():
                    remedy = "Your app key is not approved for this API family; request access in the console."
                raise ProviderError(f"AliExpress error {code}: {message}", remedy=remedy)

        if self.cache is not None and cache_key:
            self.cache.set(cache_key, payload, ttl)
        return payload

    # ---------- product surfaces ----------

    def search(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 30,
        min_price: float | None = None,
        max_price: float | None = None,
        ship_to: str | None = None,
        sort: str = "SALE_PRICE_ASC",
        currency: str | None = None,
        language: str = "EN",
        category_ids: str | None = None,
        surface: str = "affiliate",
        **_: Any,
    ) -> list[Offer]:
        """Keyword search. `surface` picks the affiliate or dropshipping API."""
        settings = self.settings
        if surface == "ds":
            method = "aliexpress.ds.text.search"
            params = {
                "keyWord": query,
                "pageIndex": page,
                "pageSize": min(page_size, 50),
                "countryCode": ship_to or settings.default_market,
                "currency": currency or settings.default_currency,
                "local": f"{language.lower()}_{(ship_to or settings.default_market).upper()}",
                "sortBy": sort,
            }
        else:
            method = "aliexpress.affiliate.product.query"
            params = {
                "keywords": query,
                "page_no": page,
                "page_size": min(page_size, 50),
                "min_sale_price": int(min_price * 100) if min_price is not None else None,
                "max_sale_price": int(max_price * 100) if max_price is not None else None,
                "ship_to_country": ship_to or settings.default_market,
                "target_currency": currency or settings.default_currency,
                "target_language": language,
                "sort": sort,
                "category_ids": category_ids,
                "tracking_id": settings.ae_tracking_id,
                "fields": (
                    "product_id,product_title,product_main_image_url,product_detail_url,"
                    "target_sale_price,target_original_price,discount,evaluate_rate,"
                    "lastest_volume,shop_id,shop_url,first_level_category_name,"
                    "ship_to_days,promotion_link"
                ),
            }

        payload = self.call(method, params)
        return [self._to_offer(item) for item in _extract_products(payload)]

    def hot_products(self, query: str | None = None, *, page: int = 1, page_size: int = 30, **kwargs: Any) -> list[Offer]:
        """Marketplace-curated high-volume listings."""
        params = {
            "keywords": query,
            "page_no": page,
            "page_size": min(page_size, 50),
            "target_currency": kwargs.get("currency") or self.settings.default_currency,
            "target_language": kwargs.get("language", "EN"),
            "ship_to_country": kwargs.get("ship_to") or self.settings.default_market,
            "tracking_id": self.settings.ae_tracking_id,
            "sort": kwargs.get("sort", "LAST_VOLUME_DESC"),
        }
        payload = self.call("aliexpress.affiliate.hotproduct.query", params)
        return [self._to_offer(item) for item in _extract_products(payload)]

    def product_detail(self, product_ids: list[str], **kwargs: Any) -> list[Offer]:
        params = {
            "product_ids": ",".join(product_ids),
            "target_currency": kwargs.get("currency") or self.settings.default_currency,
            "target_language": kwargs.get("language", "EN"),
            "ship_to_country": kwargs.get("ship_to") or self.settings.default_market,
            "tracking_id": self.settings.ae_tracking_id,
        }
        payload = self.call("aliexpress.affiliate.productdetail.get", params)
        return [self._to_offer(item) for item in _extract_products(payload)]

    def _to_offer(self, item: dict[str, Any]) -> Offer:
        price = coerce_float(first_of(item, "target_sale_price", "targetSalePrice", "app_sale_price", "salePrice"))
        original = coerce_float(first_of(item, "target_original_price", "targetOriginalPrice", "original_price"))
        discount = first_of(item, "discount", "discountRate")
        if isinstance(discount, str) and discount.endswith("%"):
            discount = coerce_float(discount)
        rating = coerce_float(first_of(item, "evaluate_rate", "evaluateRate", "averageStar", "rating"))
        if rating is not None and rating > 5:  # some fields come back as "92.5%"
            rating = round(rating / 20, 2)

        product_id = str(first_of(item, "product_id", "productId", "itemId") or "")
        return Offer(
            source="aliexpress",
            product_id=product_id,
            title=str(first_of(item, "product_title", "productTitle", "subject", "title") or ""),
            url=first_of(item, "product_detail_url", "productDetailUrl", "promotion_link", "itemUrl"),
            image=first_of(item, "product_main_image_url", "productMainImageUrl", "imageUrl"),
            currency=str(first_of(item, "target_currency", "currency") or self.settings.default_currency),
            price=price,
            original_price=original,
            discount_pct=coerce_float(discount),
            shipping_days=coerce_int(first_of(item, "ship_to_days", "shipToDays", "deliveryTime")),
            units_sold=coerce_int(first_of(item, "lastest_volume", "latestVolume", "orders", "tradeCount")),
            rating=rating,
            review_count=coerce_int(first_of(item, "evaluate_count", "evaluationCount", "reviewCount")),
            store_name=first_of(item, "shop_name", "shopName", "storeName"),
            store_id=str(first_of(item, "shop_id", "shopId") or "") or None,
            category=first_of(item, "first_level_category_name", "firstLevelCategoryName", "categoryName"),
            raw=item,
        )


def _extract_products(payload: Any) -> list[dict[str, Any]]:
    """Dig product dicts out of the Open Platform's deeply nested envelopes.

    Response shapes differ per method and per `simplify` setting, so this walks
    the tree for the first list of product-shaped dicts instead of hard-coding
    a path that will break on the next API revision.
    """
    if payload is None:
        return []

    def looks_like_product(node: Any) -> bool:
        if not isinstance(node, dict):
            return False
        keys = {k.lower().replace("_", "") for k in node}
        has_id = bool(keys & {"productid", "itemid", "id"})
        has_title = bool(keys & {"producttitle", "title", "subject", "name"})
        return has_id and has_title

    found: list[dict[str, Any]] = []

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 12 or found:
            return
        if isinstance(node, list):
            products = [n for n in node if looks_like_product(n)]
            if products:
                found.extend(products)
                return
            for child in node:
                walk(child, depth + 1)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value, depth + 1)

    walk(payload)
    return found
