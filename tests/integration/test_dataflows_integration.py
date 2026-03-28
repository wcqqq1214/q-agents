# tests/integration/test_dataflows_integration.py
from datetime import datetime

import pytest

from app.dataflows.interface import DataFlowRouter


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_stack_with_cache():
    """Test complete flow: router → provider → cache"""
    router = DataFlowRouter(enable_cache=True)

    # First call (cache miss)
    result1 = await router.get_stock_data("AAPL", datetime(2024, 1, 1), datetime(2024, 1, 31))

    assert len(result1) > 0

    # Second call (cache hit)
    result2 = await router.get_stock_data("AAPL", datetime(2024, 1, 1), datetime(2024, 1, 31))

    assert result1 == result2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_to_yfinance_fallback():
    """Test MCP failure triggers yfinance fallback"""
    config = {
        "data_vendors": {"stock_data": "mcp"},
        "tool_vendors": {},
        "mcp_servers": {
            "market_data": "http://localhost:9999",  # Invalid
            "news_search": "http://localhost:8001",
        },
        "fallback_vendor": "yfinance",
        "redis_url": "redis://localhost:6379",
    }
    router = DataFlowRouter(config, enable_cache=False)

    result = await router.get_stock_data("AAPL", datetime(2024, 1, 1), datetime(2024, 1, 31))

    assert len(result) > 0  # yfinance should succeed
