"""DuckDuckGo news search implementation."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List

from ddgs import DDGS

logger = logging.getLogger(__name__)


def search_news_impl(query: str, limit: int) -> List[dict[str, Any]]:
    """Internal implementation of news search using DuckDuckGo."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("Query is empty. Provide a company name, ticker, or topic.")

    items: List[dict[str, Any]] = []
    with DDGS() as ddgs:
        results = ddgs.news(normalized_query, max_results=limit)
        raw_list = list(results)
        logger.info("DuckDuckGo news raw count for %r: %d", normalized_query, len(raw_list))
        for entry in raw_list:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title")
            url = entry.get("url") or entry.get("link")
            source = entry.get("source")
            published_time = entry.get("date") or entry.get("published")
            snippet = entry.get("excerpt") or entry.get("body")
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
