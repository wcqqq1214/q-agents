"""MCP client for calling yfinance MCP server tools."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, List

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

load_dotenv()

# Default URLs for MCP servers
DEFAULT_MARKET_DATA_URL = "http://127.0.0.1:8000/mcp"
DEFAULT_NEWS_SEARCH_URL = "http://127.0.0.1:8001/mcp"


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
                        if isinstance(part, TextContent):
                            error_msg = part.text
                            break
                raise RuntimeError(f"MCP tool error: {error_msg}")
            if not result.content:
                raise RuntimeError("MCP tool returned empty content")
            text = ""
            for part in result.content:
                if isinstance(part, TextContent):
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
    url = os.environ.get("MCP_MARKET_DATA_URL", DEFAULT_MARKET_DATA_URL)
    return asyncio.run(_call_get_us_stock_quote_async(ticker, url))


async def _call_get_stock_data_async(ticker: str, period: str, url: str) -> dict[str, Any]:
    """Call the get_stock_data tool on the MCP server."""
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_stock_data",
                arguments={"ticker": ticker, "period": period},
            )
            if result.isError:
                error_msg = "Unknown MCP error"
                if result.content:
                    for part in result.content:
                        if isinstance(part, TextContent):
                            error_msg = part.text
                            break
                raise RuntimeError(f"MCP tool error: {error_msg}")
            if not result.content:
                raise RuntimeError("MCP tool returned empty content")
            text = ""
            for part in result.content:
                if isinstance(part, TextContent):
                    text = part.text
                    break
            if not text:
                raise RuntimeError("MCP tool returned no text content")
            return json.loads(text)


def call_get_stock_data(ticker: str, period: str = "3mo") -> dict[str, Any]:
    """Call the MCP server's get_stock_data tool.

    Args:
        ticker: Symbol to query (e.g. NVDA, AAPL, BTC-USD).
        period: History period (e.g. 1mo, 3mo, 1y). Default 3mo.

    Returns:
        A dict with ticker, last_close, sma_20, macd_line, macd_signal,
        macd_histogram, bb_middle, bb_upper, bb_lower, period_rows.
        May include error key if the request failed.

    Raises:
        RuntimeError: If the MCP server is unreachable or returns an error.
    """
    url = os.environ.get("MCP_MARKET_DATA_URL", DEFAULT_MARKET_DATA_URL)
    return asyncio.run(_call_get_stock_data_async(ticker, period, url))


async def _call_search_news_async(query: str, limit: int, url: str) -> List[dict[str, Any]]:
    """Call the search_news_with_duckduckgo tool on the MCP server."""
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_news_with_duckduckgo",
                arguments={"query": query, "limit": limit},
            )
            if result.isError:
                error_msg = "Unknown MCP error"
                if result.content:
                    for part in result.content:
                        if isinstance(part, TextContent):
                            error_msg = part.text
                            break
                raise RuntimeError(f"MCP tool error: {error_msg}")
            if not result.content:
                return []
            # Server may return a list as multiple parts (one JSON object per part).
            out: List[dict[str, Any]] = []
            for part in result.content:
                if not isinstance(part, TextContent) or not part.text:
                    continue
                data = json.loads(part.text)
                if isinstance(data, list):
                    out.extend(data)
                elif isinstance(data, dict):
                    out.append(data)
            return out


def call_search_news(query: str, limit: int = 5) -> List[dict[str, Any]]:
    """Call the MCP server's search_news_with_duckduckgo tool.

    Args:
        query: Free-form search query (e.g. AAPL, Apple Inc).
        limit: Maximum number of news results to return.

    Returns:
        A list of dicts with title, url, source, published_time, snippet.

    Raises:
        RuntimeError: If the MCP server is unreachable or returns an error.
    """
    url = os.environ.get("MCP_NEWS_SEARCH_URL", DEFAULT_NEWS_SEARCH_URL)
    return asyncio.run(_call_search_news_async(query, limit, url))


async def _call_search_news_tavily_async(query: str, limit: int, url: str) -> List[dict[str, Any]]:
    """Call the search_news_with_tavily tool on the MCP server."""
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_news_with_tavily",
                arguments={"query": query, "limit": limit},
            )
            if result.isError:
                error_msg = "Unknown MCP error"
                if result.content:
                    for part in result.content:
                        if isinstance(part, TextContent):
                            error_msg = part.text
                            break
                raise RuntimeError(f"MCP tool error: {error_msg}")
            if not result.content:
                return []
            # Server may return a list as multiple parts (one JSON object per part).
            out: List[dict[str, Any]] = []
            for part in result.content:
                if not isinstance(part, TextContent) or not part.text:
                    continue
                data = json.loads(part.text)
                if isinstance(data, list):
                    out.extend(data)
                elif isinstance(data, dict):
                    out.append(data)
            return out


def call_search_news_tavily(query: str, limit: int = 5) -> List[dict[str, Any]]:
    """Call the MCP server's search_news_with_tavily tool.

    Args:
        query: Free-form search query (e.g. AAPL, Apple Inc).
        limit: Maximum number of news results to return.

    Returns:
        A list of dicts with title, url, source, published_time, snippet.

    Raises:
        RuntimeError: If the MCP server is unreachable or returns an error.
    """
    url = os.environ.get("MCP_NEWS_SEARCH_URL", DEFAULT_NEWS_SEARCH_URL)
    return asyncio.run(_call_search_news_tavily_async(query, limit, url))


async def _call_get_stock_history_async(
    ticker: str, start_date: str, end_date: str, url: str
) -> List[dict[str, Any]]:
    """Call the get_stock_history tool on the MCP server."""
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_stock_history",
                arguments={
                    "ticker": ticker,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
            if result.isError:
                error_msg = "Unknown MCP error"
                if result.content:
                    for part in result.content:
                        if isinstance(part, TextContent):
                            error_msg = part.text
                            break
                raise RuntimeError(f"MCP tool error: {error_msg}")
            if not result.content:
                raise RuntimeError("MCP tool returned empty content")
            text = ""
            for part in result.content:
                if isinstance(part, TextContent):
                    text = part.text
                    break
            if not text:
                raise RuntimeError("MCP tool returned no text content")
            data = json.loads(text)
            # Return the data array from response
            return data.get("data", [])


def call_get_stock_history(ticker: str, start_date: str, end_date: str) -> List[dict[str, Any]]:
    """Call the MCP server's get_stock_history tool.

    Args:
        ticker: Stock symbol (e.g., AAPL, MSFT)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        List of dicts with date, open, high, low, close, volume

    Raises:
        RuntimeError: If the MCP server is unreachable or returns an error
    """
    url = os.environ.get("MCP_MARKET_DATA_URL", DEFAULT_MARKET_DATA_URL)
    return asyncio.run(_call_get_stock_history_async(ticker, start_date, end_date, url))
