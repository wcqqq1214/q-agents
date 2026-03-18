"""Polymarket API client for fetching prediction market data."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Financial-related tags to filter markets
FINANCIAL_TAGS = [
    "stocks",
    "crypto",
    "economy",
    "finance",
    "earnings",
    "fed",
    "interest-rates",
    "inflation",
    "gdp",
    "unemployment",
    "tech",
    "ai",
    "semiconductor",
    "banking",
]

# Financial categories
FINANCIAL_CATEGORIES = ["business", "economics", "crypto", "tech"]

# Financial keywords for content matching
FINANCIAL_KEYWORDS = [
    "stock",
    "earnings",
    "revenue",
    "profit",
    "market cap",
    "ipo",
    "merger",
    "acquisition",
    "share",
    "dividend",
    "eps",
    "guidance",
    "forecast",
]


class PolymarketClient:
    """Client for interacting with Polymarket Gamma API."""

    def __init__(self, base_url: str = "https://gamma-api.polymarket.com"):
        """Initialize Polymarket client.

        Args:
            base_url: Base URL for Polymarket Gamma API
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def fetch_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        closed: bool = False,
        active: Optional[bool] = None,
        tag: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch markets from Polymarket API.

        Args:
            limit: Maximum number of markets to return
            offset: Offset for pagination
            closed: Include closed markets
            active: Filter by active status
            tag: Filter by tag

        Returns:
            List of market dictionaries
        """
        url = f"{self.base_url}/markets"
        params: Dict[str, Any] = {"limit": limit, "offset": offset, "closed": closed}

        if active is not None:
            params["active"] = active
        if tag:
            params["tag"] = tag

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
        except requests.Timeout:
            logger.warning("Polymarket API request timed out")
            return []
        except requests.RequestException as e:
            logger.error(f"Polymarket API request failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Polymarket markets: {e}")
            return []

    def search_markets(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for markets related to a query.

        Args:
            query: Search query (stock ticker, company name, or keyword)
            limit: Maximum number of markets to return

        Returns:
            List of relevant market dictionaries
        """
        # First, try to fetch markets with financial tags
        all_markets: List[Dict[str, Any]] = []
        seen_ids = set()

        # Fetch markets for each financial tag
        for tag in FINANCIAL_TAGS[:5]:  # Limit to first 5 tags to avoid too many requests
            markets = self.fetch_markets(limit=20, closed=False, tag=tag)
            for market in markets:
                market_id = market.get("id") or market.get("conditionId")
                if market_id and market_id not in seen_ids:
                    all_markets.append(market)
                    seen_ids.add(market_id)

        # If no tagged markets found, fetch general active markets
        if not all_markets:
            markets = self.fetch_markets(limit=100, closed=False, active=True)
            for market in markets:
                market_id = market.get("id") or market.get("conditionId")
                if market_id and market_id not in seen_ids:
                    all_markets.append(market)
                    seen_ids.add(market_id)

        # Filter markets by query relevance
        relevant_markets = self._filter_by_query(all_markets, query)

        # Sort by relevance and volume
        relevant_markets.sort(
            key=lambda m: (
                self._calculate_relevance_score(m, query),
                float(m.get("volume24hr", 0) or 0),
            ),
            reverse=True,
        )

        return relevant_markets[:limit]

    def _filter_by_query(
        self, markets: List[Dict[str, Any]], query: str
    ) -> List[Dict[str, Any]]:
        """Filter markets by query relevance.

        Args:
            markets: List of market dictionaries
            query: Search query

        Returns:
            Filtered list of markets
        """
        query_upper = query.upper()
        relevant = []

        for market in markets:
            if self._is_relevant_market(market, query_upper):
                relevant.append(market)

        return relevant

    def _is_relevant_market(self, market: Dict[str, Any], query_upper: str) -> bool:
        """Check if a market is relevant to the query.

        Args:
            market: Market dictionary
            query_upper: Uppercase query string

        Returns:
            True if market is relevant
        """
        question = market.get("question", "").upper()
        description = market.get("description", "").upper()
        category = market.get("category", "").lower()

        # Direct match in question or description
        if query_upper in question or query_upper in description:
            return True

        # Check if it's a financial market
        if category in FINANCIAL_CATEGORIES:
            # Check for financial keywords
            if any(kw.upper() in question for kw in FINANCIAL_KEYWORDS):
                return True

        return False

    def _calculate_relevance_score(self, market: Dict[str, Any], query: str) -> float:
        """Calculate relevance score for a market.

        Args:
            market: Market dictionary
            query: Search query

        Returns:
            Relevance score (higher is more relevant)
        """
        score = 0.0
        query_upper = query.upper()
        question = market.get("question", "").upper()
        description = market.get("description", "").upper()

        # Exact match in question (highest priority)
        if query_upper in question:
            score += 10.0
            # Bonus for match at start of question
            if question.startswith(query_upper):
                score += 5.0

        # Match in description
        if query_upper in description:
            score += 5.0

        # Bonus for high volume (indicates popular/important market)
        volume_24h = float(market.get("volume24hr", 0) or 0)
        if volume_24h > 100000:
            score += 3.0
        elif volume_24h > 50000:
            score += 2.0
        elif volume_24h > 10000:
            score += 1.0

        return score

    def search_events_by_category(
        self,
        keyword: str,
        tag_id: Optional[str] = None,
        tag_label: Optional[str] = None,
        limit: int = 20,
        include_closed: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search events by keyword and filter by category tags.

        Uses the /public-search endpoint which provides better keyword search
        than the /markets endpoint. Supports pagination to fetch all results.

        Args:
            keyword: Search query string (e.g., "nvidia", "bitcoin")
            tag_id: Filter by tag ID (e.g., "120" for Finance, "21" for Crypto)
            tag_label: Filter by tag label (e.g., "finance", "crypto"), case-insensitive
            limit: Maximum number of unique results to return
            include_closed: Include closed markets in results

        Returns:
            List of event dictionaries matching the search criteria

        Example:
            >>> client = PolymarketClient()
            >>> # Search for NVIDIA events in Finance category
            >>> events = client.search_events_by_category("nvidia", tag_id="120")
            >>> # Search for Bitcoin events in Crypto category
            >>> events = client.search_events_by_category("bitcoin", tag_label="crypto")
        """
        if not keyword:
            logger.warning("Empty keyword provided to search_events_by_category")
            return []

        # Normalize tag_label for case-insensitive comparison
        if tag_label:
            tag_label = tag_label.lower()

        # Fetch events using pagination
        all_events = []
        seen_slugs = set()
        offset = 0
        page_size = 10
        max_pages = 10  # Safety limit to avoid infinite loops

        for page in range(max_pages):
            try:
                url = f"{self.base_url}/public-search"
                params = {"q": keyword, "offset": offset, "limit": page_size}

                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                events = data.get("events", [])

                if not events:
                    break

                # Deduplicate and filter events
                for event in events:
                    slug = event.get("slug")
                    if not slug or slug in seen_slugs:
                        continue

                    # Check if event is closed
                    if not include_closed and event.get("closed", False):
                        continue

                    # Filter by tag if specified
                    if tag_id or tag_label:
                        if not self._event_matches_tag(event, tag_id, tag_label):
                            continue

                    seen_slugs.add(slug)
                    all_events.append(event)

                    # Stop if we've reached the limit
                    if len(all_events) >= limit:
                        break

                if len(all_events) >= limit:
                    break

                offset += len(events)

            except requests.Timeout:
                logger.warning(f"Timeout fetching events at offset {offset}")
                break
            except requests.RequestException as e:
                logger.error(f"Error fetching events: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in search_events_by_category: {e}")
                break

        return all_events[:limit]

    def _event_matches_tag(
        self, event: Dict[str, Any], tag_id: Optional[str], tag_label: Optional[str]
    ) -> bool:
        """Check if event has a tag matching the filter criteria.

        Args:
            event: Event dictionary
            tag_id: Target tag ID (string)
            tag_label: Target tag label (lowercase string)

        Returns:
            True if event matches the tag filter (OR logic if both provided)
        """
        tags = event.get("tags", [])
        if not tags:
            return False

        for tag in tags:
            # Check tag_id match (string comparison)
            if tag_id and str(tag.get("id")) == str(tag_id):
                return True

            # Check tag_label match (case-insensitive)
            if tag_label and tag.get("label", "").lower() == tag_label:
                return True

        return False

    def parse_event_data(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and structure event data from public-search endpoint.

        Args:
            event: Raw event dictionary from API

        Returns:
            Structured event data
        """
        # Parse volume
        volume = event.get("volume", 0)
        try:
            volume = float(volume) if volume else 0.0
        except (ValueError, TypeError):
            volume = 0.0

        # Extract tags
        tags = event.get("tags", [])
        tag_labels = [tag.get("label") for tag in tags if tag.get("label")]

        # Build URL
        slug = event.get("slug", "")
        url = f"https://polymarket.com/event/{slug}" if slug else ""

        return {
            "title": event.get("title", ""),
            "slug": slug,
            "volume": volume,
            "url": url,
            "tags": tag_labels,
            "closed": event.get("closed", False),
            "description": event.get("description", "")[:200],  # Truncate long descriptions
        }

    def parse_market_data(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and structure market data.

        Args:
            market: Raw market dictionary from API

        Returns:
            Structured market data
        """
        # Parse outcome prices (probabilities)
        # outcomePrices is a JSON string like '["0.1945", "0.8055"]'
        outcome_prices_raw = market.get("outcomePrices", "[]")
        try:
            if isinstance(outcome_prices_raw, str):
                import json
                outcome_prices = json.loads(outcome_prices_raw)
            else:
                outcome_prices = outcome_prices_raw
        except Exception:
            outcome_prices = []

        prob_yes = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.0
        prob_no = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.0

        # Normalize probabilities if needed
        if prob_yes + prob_no > 0:
            total = prob_yes + prob_no
            prob_yes = prob_yes / total
            prob_no = prob_no / total

        # Parse volume (may be string or float)
        volume_24h = market.get("volume24hr", 0)
        volume_total = market.get("volume", 0)
        try:
            volume_24h = float(volume_24h) if volume_24h else 0.0
            volume_total = float(volume_total) if volume_total else 0.0
        except (ValueError, TypeError):
            volume_24h = 0.0
            volume_total = 0.0

        return {
            "question": market.get("question", ""),
            "probability_yes": round(prob_yes, 3),
            "probability_no": round(prob_no, 3),
            "volume_24h": volume_24h,
            "volume_total": volume_total,
            "liquidity": float(market.get("liquidity", 0) or 0),
            "end_date": market.get("endDate", ""),
            "category": market.get("category", ""),
            "description": market.get("description", "")[:200],  # Truncate long descriptions
            "url": f"https://polymarket.com/event/{market.get('slug', '')}",
            "active": market.get("active", False),
        }
