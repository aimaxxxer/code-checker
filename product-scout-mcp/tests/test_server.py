"""Guards on the MCP layer itself.

The SDK renamed FastMCP to MCPServer in 2.x, which is exactly the kind of
breakage that should fail a test rather than a user's first session.
"""

from __future__ import annotations

import pytest

from product_scout import server
from product_scout.providers.base import ProviderError

EXPECTED_TOOLS = {
    "provider_status", "search_supplier_catalog", "find_winning_products",
    "score_product", "estimate_unit_economics", "benchmark_retail_price",
    "check_demand_trend", "check_product_risk", "shortlist_add",
    "shortlist_list", "shortlist_remove", "scoring_model",
}


@pytest.mark.anyio
async def test_every_tool_is_registered():
    tools = await server.mcp.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS


@pytest.mark.anyio
async def test_every_tool_has_a_description():
    """An undocumented tool is one Claude will call at the wrong moment."""
    for tool in await server.mcp.list_tools():
        assert tool.description and len(tool.description) > 40, tool.name


def test_guard_converts_provider_errors_into_structured_results():
    """A missing API key must degrade one tool, not kill the session."""
    def boom():
        raise ProviderError("no key", remedy="set THE_KEY")

    result = server._guard(boom)
    assert result == {"error": "no key", "remedy": "set THE_KEY"}


def test_guard_converts_value_errors():
    def boom():
        raise ValueError("bad input")

    assert server._guard(boom) == {"error": "bad input"}


def test_guard_passes_through_success():
    assert server._guard(lambda: {"ok": True}) == {"ok": True}


def test_scoring_model_documents_every_weight():
    model = server.scoring_model()
    assert set(model["weights"]) == set(model["components"])
    assert sum(model["weights"].values()) == pytest.approx(1.0)


@pytest.fixture
def anyio_backend():
    return "asyncio"
