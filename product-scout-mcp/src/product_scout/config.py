"""Runtime configuration, loaded from the environment (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Populate os.environ from a .env file. Existing variables win."""
    path = path or Path.cwd() / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    """Everything the server needs to know, resolved once at startup."""

    # --- AliExpress Open Platform (official) ---
    ae_app_key: str | None = None
    ae_app_secret: str | None = None
    ae_tracking_id: str | None = None
    ae_gateway: str = "https://api-sg.aliexpress.com/sync"
    # The TOP gateway has accepted two timestamp encodings over the years.
    # "ms"       -> milliseconds since epoch (current AliExpress docs)
    # "datetime" -> "YYYY-MM-DD HH:MM:SS" in GMT+8 (legacy Taobao-style gateways)
    ae_timestamp_style: str = "ms"
    ae_sign_method: str = "sha256"  # or "md5"

    # --- Apify (scraper marketplace; covers Temu / Alibaba / AliExpress) ---
    apify_token: str | None = None
    apify_actor_aliexpress: str = "scrapers_lat~aliexpress-scraper"
    apify_actor_temu: str = "amit123~temu-products-scraper"
    apify_actor_alibaba: str = "devcake~alibaba-ai-search"

    # --- SerpApi (retail price benchmark + Google Trends) ---
    serpapi_key: str | None = None

    # --- Defaults ---
    default_market: str = "US"
    default_currency: str = "USD"
    default_source: str = "auto"

    # --- Infrastructure ---
    data_dir: Path = field(default_factory=lambda: Path.home() / ".product-scout")
    cache_ttl_seconds: int = 6 * 3600
    http_timeout: float = 45.0

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(_env("PRODUCT_SCOUT_DATA_DIR") or (Path.home() / ".product-scout"))
        return cls(
            ae_app_key=_env("ALIEXPRESS_APP_KEY", "AE_APP_KEY"),
            ae_app_secret=_env("ALIEXPRESS_APP_SECRET", "AE_APP_SECRET"),
            ae_tracking_id=_env("ALIEXPRESS_TRACKING_ID", "AE_TRACKING_ID", default="default"),
            ae_gateway=_env("ALIEXPRESS_GATEWAY", default="https://api-sg.aliexpress.com/sync"),
            ae_timestamp_style=_env("ALIEXPRESS_TIMESTAMP_STYLE", default="ms"),
            ae_sign_method=_env("ALIEXPRESS_SIGN_METHOD", default="sha256"),
            apify_token=_env("APIFY_TOKEN", "APIFY_API_TOKEN"),
            apify_actor_aliexpress=_env(
                "APIFY_ACTOR_ALIEXPRESS", default="scrapers_lat~aliexpress-scraper"
            ),
            apify_actor_temu=_env("APIFY_ACTOR_TEMU", default="amit123~temu-products-scraper"),
            apify_actor_alibaba=_env("APIFY_ACTOR_ALIBABA", default="devcake~alibaba-ai-search"),
            serpapi_key=_env("SERPAPI_KEY", "SERPAPI_API_KEY"),
            default_market=_env("PRODUCT_SCOUT_MARKET", default="US"),
            default_currency=_env("PRODUCT_SCOUT_CURRENCY", default="USD"),
            default_source=_env("PRODUCT_SCOUT_SOURCE", default="auto"),
            data_dir=data_dir,
            cache_ttl_seconds=int(_env_float("PRODUCT_SCOUT_CACHE_TTL", 6 * 3600)),
            http_timeout=_env_float("PRODUCT_SCOUT_HTTP_TIMEOUT", 45.0),
        )

    @property
    def aliexpress_ready(self) -> bool:
        return bool(self.ae_app_key and self.ae_app_secret)

    @property
    def apify_ready(self) -> bool:
        return bool(self.apify_token)

    @property
    def serpapi_ready(self) -> bool:
        return bool(self.serpapi_key)


_settings: Settings | None = None


def get_settings(refresh: bool = False) -> Settings:
    global _settings
    if _settings is None or refresh:
        load_dotenv()
        _settings = Settings.from_env()
        _settings.data_dir.mkdir(parents=True, exist_ok=True)
    return _settings
