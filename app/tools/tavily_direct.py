"""Direct Tavily tools that bypass MCP server.

These tools call Tavily API directly without going through the MCP server.
Use these when the MCP server is not available or for better performance.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List

from dotenv import load_dotenv
from langchain_core.tools import tool
from tavily import TavilyClient

from app.tools.finance_tools import NewsItem, _parse_news_published_time

load_dotenv()

logger = logging.getLogger(__name__)

# Initialize Tavily client
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None


@tool("search_news_tavily_direct")
def search_news_tavily_direct(query: str, limit: int = 5) -> List[NewsItem]:
    """Search recent news articles using Tavily API directly (bypasses MCP server).

    This tool queries Tavily's AI-optimized search API directly without going
    through the MCP server. Use this for better performance or when the MCP
    server is unavailable.

    Args:
        query: Free-form search query (e.g. "AAPL", "Apple Inc", "AAPL earnings").
        limit: Maximum number of news results to return.

    Returns:
        A list of NewsItem dictionaries with title, url, source, published_time, snippet.
        Returns empty list if search fails or Tavily is not configured.
    """
    if not tavily_client:
        logger.warning("Tavily client not initialized. Set TAVILY_API_KEY environment variable.")
        return []

    query_normalized = query.strip()
    if not query_normalized:
        return []

    try:
        response = tavily_client.search(
            query=query_normalized,
            search_depth="basic",
            topic="news",
            max_results=limit
        )

        results = []
        for entry in response.get("results", []):
            if not isinstance(entry, dict):
                continue

            title = entry.get("title")
            url = entry.get("url")
            source = entry.get("source")
            published_time = entry.get("published_date")
            snippet = entry.get("content")

            # Convert published_time to UTC+8 if available
            if isinstance(published_time, str):
                try:
                    iso_candidate = (
                        published_time.replace("Z", "+00:00")
                        if published_time.endswith("Z")
                        else published_time
                    )
                    dt = datetime.fromisoformat(iso_candidate)
                    dt_utc8 = (
                        dt.astimezone(timezone(timedelta(hours=8)))
                        .replace(microsecond=0)
                    )
                    published_time = dt_utc8.isoformat()
                except ValueError:
                    pass

            results.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=source,
                    published_time=published_time,
                    snippet=snippet,
                )
            )

        return results

    except Exception as exc:
        logger.warning("Tavily direct search failed for %r: %s", query_normalized, exc)
        return []


@tool("search_financial_news_tavily_direct")
def search_financial_news_tavily_direct(query: str, limit: int = 5) -> List[NewsItem]:
    """Search financial news from last 7 days via Tavily API directly (bypasses MCP server).

    This tool uses Tavily's AI-optimized search API directly and applies a 7-day
    time filter. Use this for better performance or when the MCP server is unavailable.

    Args:
        query: Search query (e.g. ticker, company name, or topic).
        limit: Max number of articles to return.

    Returns:
        List of NewsItem dicts (title, url, source, published_time, snippet).
    """
    if not tavily_client:
        logger.warning("Tavily client not initialized. Set TAVILY_API_KEY environment variable.")
        return []

    query_normalized = query.strip()
    if not query_normalized:
        return []

    try:
        response = tavily_client.search(
            query=query_normalized,
            search_depth="basic",
            topic="news",
            max_results=limit
        )

        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=7)
        out: List[NewsItem] = []

        for entry in response.get("results", []):
            if not isinstance(entry, dict):
                continue

            title = entry.get("title")
            url = entry.get("url")
            source = entry.get("source")
            published_raw = entry.get("published_date")
            snippet = entry.get("content")

            # Parse and filter by time
            published_dt = _parse_news_published_time(published_raw)
            if published_dt is None or published_dt < cutoff:
                continue

            # Convert to UTC+8 for consistency
            if isinstance(published_raw, str):
                try:
                    iso_candidate = (
                        published_raw.replace("Z", "+00:00")
                        if published_raw.endswith("Z")
                        else published_raw
                    )
                    dt = datetime.fromisoformat(iso_candidate)
                    dt_utc8 = (
                        dt.astimezone(timezone(timedelta(hours=8)))
                        .replace(microsecond=0)
                    )
                    published_raw = dt_utc8.isoformat()
                except ValueError:
                    pass

            out.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=source,
                    published_time=published_raw,
                    snippet=snippet,
                )
            )

        if not out and response.get("results"):
            logger.info(
                "search_financial_news_tavily_direct: All results filtered out for query=%r",
                query_normalized,
            )

        return out

    except Exception as exc:
        logger.warning(
            "search_financial_news_tavily_direct failed for query=%r: %s",
            query_normalized,
            exc,
            exc_info=True,
        )
        return []
