# tests/test_dataflows_mcp_provider.py
from datetime import datetime

import pytest

from app.dataflows.base import ProviderError
from app.dataflows.models import StockCandle
from app.dataflows.providers.mcp_provider import MCPDataProvider


@pytest.mark.asyncio
async def test_mcp_provider_get_stock_data():
    """Test MCP provider returns standardized StockCandle"""
    config = {"mcp_servers": {"market_data": "http://localhost:8000"}}
    provider = MCPDataProvider(config)

    # Try to call MCP server, skip if not running
    try:
        result = await provider.get_stock_data("AAPL", datetime(2024, 1, 1), datetime(2024, 1, 31))

        assert isinstance(result, list)
        if result:  # If MCP server is running
            assert isinstance(result[0], StockCandle)
            assert result[0].symbol == "AAPL"
    except ProviderError as e:
        # MCP server not running, skip test
        pytest.skip(f"MCP server not available: {e}")
