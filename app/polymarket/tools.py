"""LangChain tools for Polymarket prediction market data."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_core.tools import tool

from app.polymarket.client import PolymarketClient

logger = logging.getLogger(__name__)


@tool("search_polymarket_predictions")
def search_polymarket_predictions(query: str, limit: int = 10) -> str:
    """Search Polymarket for prediction markets related to a stock or financial event.

    Args:
        query: Stock ticker, company name, or financial event keyword
        limit: Maximum number of markets to return (default: 10)

    Returns:
        JSON string containing relevant prediction markets with probabilities,
        volumes, and market sentiment.
    """
    try:
        client = PolymarketClient()
        markets = client.search_markets(query=query, limit=limit)

        # Parse and structure market data
        parsed_markets = [client.parse_market_data(m) for m in markets]

        result: Dict[str, Any] = {
            "query": query,
            "markets_found": len(parsed_markets),
            "markets": parsed_markets,
            "meta": {
                "source": "polymarket",
                "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"Error searching Polymarket predictions: {e}")
        # Return empty result on error
        return json.dumps(
            {
                "query": query,
                "markets_found": 0,
                "markets": [],
                "meta": {
                    "source": "polymarket",
                    "error": str(e),
                    "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                },
            }
        )


@tool("search_polymarket_by_category")
def search_polymarket_by_category(
    keyword: str,
    category: str = "finance",
    limit: int = 10,
    include_closed: bool = False,
) -> str:
    """Search Polymarket events by keyword and filter by category.

    This tool uses the public-search endpoint which provides better keyword
    matching than the general market search. Useful for finding prediction
    markets in specific categories like Finance, Crypto, or Politics.

    Args:
        keyword: Search keyword (e.g., "nvidia", "bitcoin", "trump")
        category: Category to filter by. Options: "finance", "crypto", "politics",
                 "tech", "business", "sports". Default: "finance"
        limit: Maximum number of events to return (default: 10)
        include_closed: Include closed markets in results (default: False)

    Returns:
        JSON string containing matching events with titles, volumes, URLs, and tags.

    Example:
        >>> search_polymarket_by_category("nvidia", category="finance", limit=5)
        >>> search_polymarket_by_category("bitcoin", category="crypto")
        >>> search_polymarket_by_category("trump", category="politics")
    """
    # Map category names to tag IDs
    CATEGORY_TAG_IDS = {
        "finance": "120",
        "crypto": "21",
        "politics": "2",
        "tech": "1401",
        "business": "107",
        "sports": "5",
    }

    try:
        client = PolymarketClient()

        # Get tag_id for the category
        tag_id = CATEGORY_TAG_IDS.get(category.lower())
        if not tag_id:
            available = ", ".join(CATEGORY_TAG_IDS.keys())
            return json.dumps(
                {
                    "error": f"Invalid category '{category}'. Available: {available}",
                    "keyword": keyword,
                    "events_found": 0,
                    "events": [],
                }
            )

        # Search events
        events = client.search_events_by_category(
            keyword=keyword,
            tag_id=tag_id,
            tag_label=category.lower(),
            limit=limit,
            include_closed=include_closed,
        )

        # Parse event data
        parsed_events = [client.parse_event_data(e) for e in events]

        result: Dict[str, Any] = {
            "keyword": keyword,
            "category": category,
            "events_found": len(parsed_events),
            "events": parsed_events,
            "meta": {
                "source": "polymarket",
                "endpoint": "public-search",
                "include_closed": include_closed,
                "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"Error searching Polymarket by category: {e}")
        return json.dumps(
            {
                "keyword": keyword,
                "category": category,
                "events_found": 0,
                "events": [],
                "meta": {
                    "source": "polymarket",
                    "error": str(e),
                    "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                },
            }
        )

