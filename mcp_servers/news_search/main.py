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
from typing import Any, List

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables from .env file
load_dotenv()

from mcp_servers.news_search.duckduckgo_impl import search_news_impl as ddg_search
from mcp_servers.news_search.tavily_impl import search_news_impl as tavily_search

mcp = FastMCP("news-search-server", json_response=True)


@mcp.tool()
def search_news_with_duckduckgo(query: str, limit: int = 5) -> List[dict[str, Any]]:
    """Search recent news articles using DuckDuckGo for a given query string.

    Use this when the user asks for the latest news, headlines, or events
    related to a company, stock ticker, or macro theme.

    Args:
        query: Free-form search query (e.g. AAPL, Apple Inc, AAPL earnings).
        limit: Maximum number of news results to return.

    Returns:
        A list of dicts with title, url, source, published_time, snippet.
        Returns empty list if search fails.
    """
    return ddg_search(query, limit)


@mcp.tool()
def search_news_with_tavily(query: str, limit: int = 5) -> List[dict[str, Any]]:
    """Search recent news articles using Tavily API for a given query string.

    Use this when the user asks for the latest news, headlines, or events
    related to a company, stock ticker, or macro theme. Tavily provides
    high-quality, AI-optimized search results specifically for news content.

    Args:
        query: Free-form search query (e.g. AAPL, Apple Inc, AAPL earnings).
        limit: Maximum number of news results to return.

    Returns:
        A list of dicts with title, url, source, published_time, snippet.
        Returns empty list if search fails or Tavily is not configured.
    """
    return tavily_search(query, limit)


def main() -> None:
    """Run the MCP server with streamable HTTP transport."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    host = os.environ.get("MCP_NEWS_SEARCH_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_NEWS_SEARCH_PORT", "8001"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
