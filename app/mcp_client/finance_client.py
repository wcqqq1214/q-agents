"""Unified MCP client helpers for finance and news tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from app.mcp_client.config import ensure_mcp_endpoint
from app.mcp_client.connection_manager import (
    MCPToolExecutionError,
    get_mcp_connection_manager,
)

load_dotenv()


def _extract_tool_error_text(content: list[Any] | None) -> str:
    if not content:
        return "Unknown MCP tool error"
    for part in content:
        if isinstance(part, TextContent) and part.text:
            return part.text
    return "Unknown MCP tool error"


def _decode_result_content(content: list[Any] | None) -> Any:
    if not content:
        return None

    decoded_parts: list[Any] = []
    for part in content:
        if not isinstance(part, TextContent) or not part.text:
            continue
        try:
            decoded_parts.append(json.loads(part.text))
        except Exception:
            decoded_parts.append(part.text)

    if not decoded_parts:
        return None
    if len(decoded_parts) == 1:
        return decoded_parts[0]
    return decoded_parts


async def _call_tool_via_url_async(
    url: str, tool_name: str, arguments: dict[str, Any] | None = None
) -> Any:
    normalized_url = ensure_mcp_endpoint(url)
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        async with streamable_http_client(normalized_url, http_client=http_client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments or {})
                if result.isError:
                    raise MCPToolExecutionError(_extract_tool_error_text(result.content))
                return _decode_result_content(result.content)


async def _call_tool_async(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    url: str | None = None,
) -> Any:
    if url:
        return await _call_tool_via_url_async(url, tool_name, arguments)
    manager = get_mcp_connection_manager()
    return await manager.call_tool_json(server_name, tool_name, arguments)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _call_get_us_stock_quote_async(
    ticker: str, url: str | None = None
) -> dict[str, Any]:
    payload = await _call_tool_async(
        "market_data",
        "get_us_stock_quote",
        {"ticker": ticker},
        url=url,
    )
    return payload if isinstance(payload, dict) else {}


def call_get_us_stock_quote(ticker: str, url: str | None = None) -> dict[str, Any]:
    """Call the MCP market-data server's `get_us_stock_quote` tool."""

    return _run(_call_get_us_stock_quote_async(ticker, url=url))


async def _call_get_stock_data_async(
    ticker: str, period: str, url: str | None = None
) -> dict[str, Any]:
    payload = await _call_tool_async(
        "market_data",
        "get_stock_data",
        {"ticker": ticker, "period": period},
        url=url,
    )
    return payload if isinstance(payload, dict) else {}


def call_get_stock_data(
    ticker: str, period: str = "3mo", url: str | None = None
) -> dict[str, Any]:
    """Call the MCP market-data server's `get_stock_data` tool."""

    return _run(_call_get_stock_data_async(ticker, period, url=url))


async def _call_search_news_async(
    query: str, limit: int, url: str | None = None
) -> list[dict[str, Any]]:
    payload = await _call_tool_async(
        "news_search",
        "search_news_with_duckduckgo",
        {"query": query, "limit": limit},
        url=url,
    )
    return _extract_articles_payload(payload, source="duckduckgo")


def call_search_news(
    query: str, limit: int = 5, url: str | None = None
) -> list[dict[str, Any]]:
    """Call the MCP news-search server's DuckDuckGo-backed tool."""

    return _run(_call_search_news_async(query, limit, url=url))


async def _call_search_news_tavily_async(
    query: str, limit: int, url: str | None = None
) -> list[dict[str, Any]]:
    payload = await _call_tool_async(
        "news_search",
        "search_news_with_tavily",
        {"query": query, "limit": limit},
        url=url,
    )
    return _extract_articles_payload(payload, source="tavily")


def call_search_news_tavily(
    query: str, limit: int = 5, url: str | None = None
) -> list[dict[str, Any]]:
    """Call the MCP news-search server's Tavily-backed tool."""

    return _run(_call_search_news_tavily_async(query, limit, url=url))


async def _call_get_stock_history_async(
    ticker: str,
    start_date: str,
    end_date: str,
    url: str | None = None,
) -> list[dict[str, Any]]:
    payload = await _call_tool_async(
        "market_data",
        "get_stock_history",
        {
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
        },
        url=url,
    )
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", [])
    return data if isinstance(data, list) else []


def call_get_stock_history(
    ticker: str, start_date: str, end_date: str, url: str | None = None
) -> list[dict[str, Any]]:
    """Call the MCP market-data server's `get_stock_history` tool."""

    return _run(_call_get_stock_history_async(ticker, start_date, end_date, url=url))


def _extract_articles_payload(payload: Any, *, source: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        error = payload.get("error")
        if error:
            raise RuntimeError(str(error))
        articles = payload.get("articles", [])
        if isinstance(articles, list):
            return [item for item in articles if isinstance(item, dict)]
        raise RuntimeError(f"MCP {source} response used an invalid articles payload")

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    return []
