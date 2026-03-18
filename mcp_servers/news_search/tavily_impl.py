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
        logger.warning("Tavily client not initialized. Set TAVILY_API_KEY environment variable.")
        return []

    items: List[dict[str, Any]] = []
    try:
        response = tavily_client.search(
            query=query.strip(),
            search_depth="basic",
            topic="news",
            max_results=limit
        )
        logger.info("Tavily news raw count for %r: %d", query, len(response.get("results", [])))

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

            items.append({
                "title": title,
                "url": url,
                "source": source,
                "published_time": published_time,
                "snippet": snippet,
            })
    except Exception as exc:
        logger.warning("Tavily news search failed for %r: %s", query, exc)

    return items
