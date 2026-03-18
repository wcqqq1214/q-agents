"""Polygon API client with strict rate limiting.

This module provides functions to fetch OHLC and news data from Polygon.io
with built-in rate limiting to respect the free tier limit of 5 requests/minute.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.polygon.io"

# Rate limiting state (module-level)
_REQUEST_TIMES: List[float] = []
MAX_REQUESTS_PER_MINUTE = 5
SAFETY_BUFFER_SECONDS = 0.5


def _get_api_key() -> str:
    """Get Polygon API key from environment variable.

    Returns:
        The API key string.

    Raises:
        RuntimeError: If POLYGON_API_KEY is not set.
    """
    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        raise RuntimeError(
            "POLYGON_API_KEY environment variable is not set. "
            "Please add it to your .env file."
        )
    return api_key


def rate_limit() -> None:
    """Block execution until we can safely make another API request.

    This function implements a sliding window rate limiter that ensures
    we never exceed MAX_REQUESTS_PER_MINUTE requests in any 60-second window.
    It adds a safety buffer to prevent edge cases.
    """
    global _REQUEST_TIMES

    now = time.time()

    # Remove timestamps older than 60 seconds
    _REQUEST_TIMES = [t for t in _REQUEST_TIMES if now - t < 60]

    # If we've hit the limit, wait until the oldest request is 60+ seconds old
    if len(_REQUEST_TIMES) >= MAX_REQUESTS_PER_MINUTE:
        oldest_request = _REQUEST_TIMES[0]
        wait_time = 60 - (now - oldest_request) + SAFETY_BUFFER_SECONDS

        if wait_time > 0:
            logger.info(f"Rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)

    # Record this request
    _REQUEST_TIMES.append(time.time())


def _http_get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    max_retries: int = 5,
    backoff: float = 2.0,
) -> requests.Response:
    """Execute HTTP GET with exponential backoff and 429 handling.

    Args:
        url: The URL to request.
        params: Query parameters.
        max_retries: Maximum number of retry attempts.
        backoff: Base backoff multiplier for exponential backoff.

    Returns:
        The HTTP response object.

    Raises:
        requests.RequestException: If all retries are exhausted.
    """
    headers = {"Authorization": f"Bearer {_get_api_key()}"}

    for attempt in range(max_retries):
        try:
            resp = requests.get(
                url,
                params=params or {},
                headers=headers,
                timeout=30,
            )
        except requests.RequestException as exc:
            if attempt == max_retries - 1:
                raise
            wait = (backoff ** attempt) + 0.5
            logger.warning(f"Request failed: {exc}. Retrying in {wait:.1f}s...")
            time.sleep(wait)
            continue

        # Handle rate limiting (429)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = (
                float(retry_after)
                if retry_after and retry_after.isdigit()
                else min((backoff ** attempt) + 1.0, 60.0)
            )
            logger.warning(f"Rate limited (429). Waiting {wait:.1f}s...")
            time.sleep(wait)
            if attempt == max_retries - 1:
                resp.raise_for_status()
            continue

        # Handle server errors (5xx)
        if 500 <= resp.status_code < 600:
            wait = min((backoff ** attempt) + 1.0, 60.0)
            logger.warning(
                f"Server error {resp.status_code}. Retrying in {wait:.1f}s..."
            )
            time.sleep(wait)
            if attempt == max_retries - 1:
                resp.raise_for_status()
            continue

        # Raise for other HTTP errors
        resp.raise_for_status()
        return resp

    raise RuntimeError("Unreachable code path")


def fetch_ohlc(ticker: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Fetch daily OHLC data from Polygon for a given ticker and date range.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.

    Returns:
        List of dictionaries containing OHLC data with keys:
        - date: Trading date (YYYY-MM-DD)
        - open, high, low, close: Price data
        - volume: Trading volume

    Raises:
        requests.RequestException: If the API request fails.
    """
    rate_limit()

    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
    }

    logger.info(f"Fetching OHLC for {ticker} from {start_date} to {end_date}")
    resp = _http_get(url, params=params)
    data = resp.json()

    results = data.get("results") or []
    rows = []

    for r in results:
        timestamp_ms = int(r["t"])
        date_str = (
            datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            .date()
            .isoformat()
        )

        rows.append({
            "date": date_str,
            "open": r.get("o"),
            "high": r.get("h"),
            "low": r.get("l"),
            "close": r.get("c"),
            "volume": r.get("v"),
        })

    logger.info(f"Fetched {len(rows)} OHLC rows for {ticker}")
    return rows


def fetch_news(
    ticker: str,
    start_date: str,
    end_date: str,
    per_page: int = 50,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch news articles from Polygon for a given ticker and date range.

    This function handles pagination automatically and respects rate limits.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        per_page: Number of articles per page (max 50).
        max_pages: Maximum number of pages to fetch (None = all pages).

    Returns:
        List of dictionaries containing news data with keys:
        - id: Unique article ID
        - symbol: Stock ticker
        - published_utc: Publication timestamp
        - title: Article title
        - description: Article description/summary
        - article_url: URL to full article
        - publisher: Publisher name

    Raises:
        requests.RequestException: If the API request fails.
    """
    url = f"{BASE_URL}/v2/reference/news"
    params = {
        "ticker": ticker,
        "published_utc.gte": start_date,
        "published_utc.lte": end_date,
        "limit": per_page,
        "order": "asc",
    }

    all_articles: List[Dict[str, Any]] = []
    seen_ids: set = set()
    pages = 0
    next_url: Optional[str] = None

    logger.info(f"Fetching news for {ticker} from {start_date} to {end_date}")

    while True:
        rate_limit()

        try:
            resp = _http_get(next_url or url, params=None if next_url else params)
        except requests.RequestException as exc:
            logger.error(f"Failed to fetch news page {pages + 1}: {exc}")
            break

        data = resp.json()
        results = data.get("results") or []

        if not results:
            logger.info(f"No more results after page {pages}")
            break

        page_articles = 0
        for r in results:
            article_id = r.get("id")
            if article_id and article_id in seen_ids:
                continue

            publisher_obj = r.get("publisher") or {}

            article = {
                "id": article_id,
                "symbol": ticker,
                "published_utc": r.get("published_utc"),
                "title": r.get("title"),
                "description": r.get("description"),
                "article_url": r.get("article_url"),
                "publisher": publisher_obj.get("name"),
            }

            all_articles.append(article)
            page_articles += 1
            if article_id:
                seen_ids.add(article_id)

        pages += 1
        logger.info(f"Page {pages}: fetched {page_articles} articles (total: {len(all_articles)})")

        next_url = data.get("next_url")

        if max_pages is not None and pages >= max_pages:
            logger.info(f"Reached max_pages limit ({max_pages})")
            break

        if not next_url:
            logger.info(f"No more pages available")
            break

    logger.info(f"Fetched {len(all_articles)} news articles for {ticker} across {pages} pages")
    return all_articles
