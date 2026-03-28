from datetime import datetime

import pytest

from app.dataflows.interface import DataFlowRouter


@pytest.mark.asyncio
async def test_router_primary_success():
    """Test router uses primary provider when available"""
    config = {
        "data_vendors": {"stock_data": "mcp"},
        "tool_vendors": {},
        "mcp_servers": {
            "market_data": "http://localhost:8000",
            "news_search": "http://localhost:8001",
        },
        "redis_url": "redis://localhost:6379",
    }
    router = DataFlowRouter(config, enable_cache=False)

    result = await router.get_stock_data("AAPL", datetime(2024, 1, 1), datetime(2024, 1, 31))

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_router_fallback_on_error():
    """Test router falls back to yfinance when MCP fails"""
    config = {
        "data_vendors": {"stock_data": "mcp"},
        "tool_vendors": {},
        "mcp_servers": {
            "market_data": "http://invalid:9999",  # Invalid URL
            "news_search": "http://localhost:8001",
        },
        "fallback_vendor": "yfinance",
        "redis_url": "redis://localhost:6379",
    }
    router = DataFlowRouter(config, enable_cache=False)

    # Should fallback to yfinance
    result = await router.get_stock_data("AAPL", datetime(2024, 1, 1), datetime(2024, 1, 31))

    assert isinstance(result, list)
    assert len(result) > 0
