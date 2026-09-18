from __future__ import annotations

import pytest

from product_scout.config import Settings
from product_scout.pipeline import Scout, relevance
from product_scout.providers.base import ProviderError, coerce_float, coerce_int


@pytest.fixture
def scout(tmp_path) -> Scout:
    return Scout(Settings(data_dir=tmp_path))


def test_relevance_scoring():
    assert relevance("Foldable Neck Massager with Heat", "neck massager") == 1.0
    assert relevance("Clear Phone Case", "neck massager") == 0.0
    assert relevance("Neck Pillow Travel", "neck massager") == pytest.approx(0.5)
    assert relevance("anything", "") == 1.0


def test_falls_back_to_demo_without_credentials(scout):
    provider, reason = scout.resolve_source("aliexpress")
    assert provider == "demo"
    assert "no credentials" in reason.lower()


def test_temu_routes_to_apify_when_configured(tmp_path):
    scout = Scout(Settings(data_dir=tmp_path, apify_token="tok"))
    provider, reason = scout.resolve_source("temu")
    assert provider == "apify"
    assert "no public product api" in reason.lower()


def test_official_api_is_preferred_over_scraping(tmp_path):
    scout = Scout(Settings(data_dir=tmp_path, ae_app_key="k", ae_app_secret="s", apify_token="tok"))
    assert scout.resolve_source("aliexpress")[0] == "aliexpress"


def test_unknown_marketplace_raises_with_a_remedy(scout):
    with pytest.raises(ProviderError) as exc:
        scout.resolve_source("wish")
    assert exc.value.remedy and "aliexpress" in exc.value.remedy


def test_pipeline_runs_end_to_end_without_credentials(scout):
    report = scout.find_winners("neck massager", marketplace="demo", limit=5)
    assert report["results"]
    for row in report["results"]:
        assert 0 <= row["score"]["total"] <= 100
        assert row["pricing_basis"] in {"retail_benchmark", "target_markup", "none"}
        assert "rank_score" in row


def test_unmatched_listings_are_not_priced_off_the_benchmark(scout):
    """The core guard: a $0.62 phone case must not inherit a massager's retail price."""
    report = scout.find_winners("neck massager", marketplace="demo", limit=10)
    for row in report["results"]:
        if row["query_relevance"] < 0.5:
            assert row["pricing_basis"] == "target_markup"
            assert row["score"]["components"].get("margin", 0) <= 55.0


def test_matched_listings_outrank_unmatched_ones(scout):
    report = scout.find_winners("neck massager", marketplace="demo", limit=10)
    top = report["results"][0]
    assert top["query_relevance"] >= 0.5
    assert top["pricing_basis"] == "retail_benchmark"


def test_results_are_sorted_by_rank_score(scout):
    report = scout.find_winners("massager", marketplace="demo", limit=10)
    ranks = [row["rank_score"] for row in report["results"]]
    assert ranks == sorted(ranks, reverse=True)


def test_min_score_filters_results(scout):
    everything = scout.find_winners("massager", marketplace="demo", limit=20, min_score=0)
    filtered = scout.find_winners("massager", marketplace="demo", limit=20, min_score=70)
    assert len(filtered["results"]) < len(everything["results"])
    assert all(row["score"]["total"] >= 70 for row in filtered["results"])


def test_status_reports_what_is_missing(scout):
    status = scout.status()
    assert status["live_data_available"] is False
    assert status["providers"]["aliexpress_official"]["configured"] is False
    assert "portals.aliexpress.com" in status["providers"]["aliexpress_official"]["setup"]


def test_synthetic_data_is_labelled_as_such(scout):
    """Fake data that does not announce itself is worse than no data."""
    bench = scout.benchmark("neck massager")
    trend = scout.trend("neck massager")
    assert "SYNTHETIC" in (bench.note or "")
    assert "SYNTHETIC" in (trend.note or "")


@pytest.mark.parametrize("raw,expected", [
    ("$12.34", 12.34), ("US $1,234.56", 1234.56), ("1.234,56", 1234.56),
    ("12", 12.0), ("", None), (None, None), ("free", None),
])
def test_price_parsing_handles_marketplace_formats(raw, expected):
    assert coerce_float(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("1.2K sold", 1200), ("3M+", 3000000), ("450", 450), ("", None), (None, None),
])
def test_count_parsing_handles_shorthand(raw, expected):
    assert coerce_int(raw) == expected
