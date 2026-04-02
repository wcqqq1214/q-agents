"""MCP server exposing DuckDuckGo and Tavily news search via MCP tools."""

from __future__ import annotations

import sys
from pathlib import Path

# When run as script, ensure project root is on path
if __name__ != "__main__" or getattr(sys, "frozen", False):
    _root = None
else:
    _root = Path(__file__).resolve().parents[2]
    if _root and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import logging
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

# Load environment variables from .env file
load_dotenv()

from mcp_servers.common.tool_errors import build_tool_error_payload
from mcp_servers.news_search.duckduckgo_impl import search_news_impl as ddg_search
from mcp_servers.news_search.tavily_impl import search_news_impl as tavily_search

mcp = FastMCP("news-search-server", json_response=True)


@mcp.tool()
def search_news_with_duckduckgo(query: str, limit: int = 5) -> dict[str, Any]:
    """Search recent news articles using DuckDuckGo for a given query string.

    Use this when the user asks for the latest news, headlines, or events
    related to a company, stock ticker, or macro theme.

    Args:
        query: Free-form search query (e.g. AAPL, Apple Inc, AAPL earnings).
        limit: Maximum number of news results to return.

    Returns:
        Dict with:
        - articles: list of dicts with title, url, source, published_time, snippet
        - source: "duckduckgo"
        - error / retryable / retry_after_seconds when upstream search fails
    """
    try:
        return {
            "articles": ddg_search(query, limit),
            "source": "duckduckgo",
        }
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "DuckDuckGo news search failed for %r: %s", query, exc
        )
        return build_tool_error_payload(
            provider_name="DuckDuckGo News",
            tool_name="search_news_with_duckduckgo",
            exc=exc,
            base_payload={"articles": [], "source": "duckduckgo"},
        )


@mcp.tool()
def search_news_with_tavily(query: str, limit: int = 5) -> dict[str, Any]:
    """Search recent news articles using Tavily API for a given query string.

    Use this when the user asks for the latest news, headlines, or events
    related to a company, stock ticker, or macro theme. Tavily provides
    high-quality, AI-optimized search results specifically for news content.

    Args:
        query: Free-form search query (e.g. AAPL, Apple Inc, AAPL earnings).
        limit: Maximum number of news results to return.

    Returns:
        Dict with:
        - articles: list of dicts with title, url, source, published_time, snippet
        - source: "tavily"
        - error / retryable / retry_after_seconds when upstream search fails
    """
    try:
        return {
            "articles": tavily_search(query, limit),
            "source": "tavily",
        }
    except Exception as exc:
        logging.getLogger(__name__).warning("Tavily news search failed for %r: %s", query, exc)
        return build_tool_error_payload(
            provider_name="Tavily News",
            tool_name="search_news_with_tavily",
            exc=exc,
            base_payload={"articles": [], "source": "tavily"},
        )


def build_app() -> FastAPI:
    """Create an ASGI app with MCP and health endpoints."""

    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "server": "news_search",
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }

    app.mount("/", mcp.streamable_http_app())
    return app


def main() -> None:
    """Run the MCP server with streamable HTTP transport."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    host = os.environ.get("MCP_NEWS_SEARCH_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_NEWS_SEARCH_PORT", "8001"))
    uvicorn.run(build_app(), host=host, port=port)


if __name__ == "__main__":
    main()
