"""Tavily news search implementation."""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, List

from tavily import TavilyClient

logger = logging.getLogger(__name__)

# Initialize Tavily client
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None


def search_news_impl(query: str, limit: int) -> List[dict[str, Any]]:
    """Internal implementation of news search using Tavily API."""
    if not tavily_client:
        raise RuntimeError("Tavily client not initialized. Set TAVILY_API_KEY to enable this tool.")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("Query is empty. Provide a company name, ticker, or topic.")

    items: List[dict[str, Any]] = []
    response = tavily_client.search(
        query=normalized_query, search_depth="basic", topic="news", max_results=limit
    )
    logger.info("Tavily news raw count for %r: %d", normalized_query, len(response.get("results", [])))

    for entry in response.get("results", []):
        if not isinstance(entry, dict):
            continue

        title = entry.get("title")
        url = entry.get("url")
        source = entry.get("source")
        published_time = entry.get("published_date")
        snippet = entry.get("content")

        if isinstance(published_time, str):
            try:
                iso_candidate = (
                    published_time.replace("Z", "+00:00")
                    if published_time.endswith("Z")
                    else published_time
                )
                dt = datetime.fromisoformat(iso_candidate)
                dt_utc8 = dt.astimezone(timezone(timedelta(hours=8))).replace(microsecond=0)
                published_time = dt_utc8.isoformat()
            except ValueError:
                pass

        items.append(
            {
                "title": title,
                "url": url,
                "source": source,
                "published_time": published_time,
                "snippet": snippet,
            }
        )

    return items
