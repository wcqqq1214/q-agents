"""MCP client for calling yfinance MCP server tools."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv()

DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"


async def _call_get_us_stock_quote_async(ticker: str, url: str) -> dict[str, Any]:
    """Call the get_us_stock_quote tool on the MCP yfinance server."""
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_us_stock_quote",
                arguments={"ticker": ticker},
            )
            if result.isError:
                error_msg = "Unknown MCP error"
                if result.content:
                    for part in result.content:
                        if hasattr(part, "text"):
                            error_msg = part.text
                            break
                raise RuntimeError(f"MCP tool error: {error_msg}")
            if not result.content:
                raise RuntimeError("MCP tool returned empty content")
            text = ""
            for part in result.content:
                if hasattr(part, "text"):
                    text = part.text
                    break
            if not text:
                raise RuntimeError("MCP tool returned no text content")
            return json.loads(text)


def call_get_us_stock_quote(ticker: str) -> dict[str, Any]:
    """Call the MCP yfinance server's get_us_stock_quote tool.

    Args:
        ticker: The US stock ticker symbol (e.g. AAPL, MSFT).

    Returns:
        A dict matching StockQuote structure (symbol, price, currency, etc.).

    Raises:
        RuntimeError: If the MCP server is unreachable or returns an error.
    """
    url = os.environ.get("MCP_YFINANCE_URL", DEFAULT_MCP_URL)
    return asyncio.run(_call_get_us_stock_quote_async(ticker, url))
