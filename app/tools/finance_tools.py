from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, TypedDict

from ddgs import DDGS
from langchain_core.tools import tool

from app.mcp_client.finance_client import call_get_us_stock_quote


def _now_iso_utc8() -> str:
    """Return current time in ISO8601 format using UTC+8 timezone without microseconds."""

    return (
        datetime.now(timezone.utc)
        .astimezone(timezone(timedelta(hours=8)))
        .replace(microsecond=0)
        .isoformat()
    )


class StockQuote(TypedDict, total=False):
    """Typed dictionary representing a single stock quote.

    Attributes:
        symbol: The stock ticker symbol, such as ``\"AAPL\"`` or ``\"MSFT\"``.
        currency: The trading currency code (for example, ``\"USD\"``).
        price: The latest traded price for the symbol.
        change: The absolute price change compared to the previous close.
        change_percent: The percentage price change compared to the previous close.
        previous_close: The previous trading day's closing price.
        open: The current trading day's opening price.
        day_high: The highest traded price during the current trading day.
        day_low: The lowest traded price during the current trading day.
        volume: The most recent traded volume for the current trading day.
        timestamp: ISO8601 string representing the time when the quote was retrieved.
        error: Optional error message if the quote could not be retrieved successfully.
    """

    symbol: str
    currency: Optional[str]
    price: Optional[float]
    change: Optional[float]
    change_percent: Optional[float]
    previous_close: Optional[float]
    open: Optional[float]
    day_high: Optional[float]
    day_low: Optional[float]
    volume: Optional[float]
    timestamp: Optional[str]
    error: Optional[str]


class NewsItem(TypedDict, total=False):
    """Typed dictionary representing a single news article.

    Attributes:
        title: The headline of the news article.
        url: The canonical URL pointing to the full article.
        source: The publisher or website name, such as ``\"Reuters\"`` or
            ``\"Yahoo Finance\"``.
        published_time: The article's publication time as a human-readable
            string. The exact format depends on the underlying data returned
            by DuckDuckGo and is not guaranteed to be ISO8601.
        snippet: A short excerpt or summary describing the article content.
    """

    title: Optional[str]
    url: Optional[str]
    source: Optional[str]
    published_time: Optional[str]
    snippet: Optional[str]


@tool("get_us_stock_quote")
def get_us_stock_quote(ticker: str) -> StockQuote:
    """Fetch the latest quote for a single US stock ticker using Yahoo Finance.

    This tool is intended for retrieving a quick snapshot of the most recent
    market data for a US-listed equity. It is useful when the user asks for
    the latest price, price change, or intraday statistics about a single
    stock such as \"AAPL\" or \"MSFT\".

    The tool uses the public Yahoo Finance backend via the ``yfinance`` library,
    so values may be delayed and are not guaranteed to be suitable for trading
    or risk management. Treat all numbers as indicative only.

    Args:
        ticker: The US stock ticker symbol to query. Examples include
            ``\"AAPL\"``, ``\"MSFT\"``, or ``\"GOOGL\"``. The symbol should be
            provided without an exchange suffix for standard US listings.

    Returns:
        A ``StockQuote`` typed dictionary containing the latest available
        market data for the requested symbol. On success, the dictionary
        typically includes:

        - ``symbol``: Echo of the requested ticker.
        - ``currency``: Trading currency code (for example, ``\"USD\"``).
        - ``price``: Latest traded price, if available.
        - ``change``: Absolute price change versus previous close.
        - ``change_percent``: Percentage change versus previous close.
        - ``previous_close``: Previous session's official close, if available.
        - ``open``: Current session's opening price, if available.
        - ``day_high`` / ``day_low``: Intraday high and low prices.
        - ``volume``: Most recent trading volume.
        - ``timestamp``: ISO8601 timestamp when the quote was fetched.

        If the ticker is invalid, data is missing, or an unexpected error
        occurs, the returned dictionary still contains a ``symbol`` field and
        may include an ``error`` field with a human-readable explanation.
        In such cases, numeric fields can be ``None``.
    """

    normalized = ticker.strip().upper() if ticker is not None else ""
    if not normalized:
        return StockQuote(
            symbol="",
            currency=None,
            price=None,
            change=None,
            change_percent=None,
            previous_close=None,
            open=None,
            day_high=None,
            day_low=None,
            volume=None,
            timestamp=_now_iso_utc8(),
            error=(
                "Ticker symbol is empty. Please provide a valid US stock "
                "ticker such as 'AAPL' or 'MSFT'."
            ),
        )

    try:
        result = call_get_us_stock_quote(normalized)
        return StockQuote(
            symbol=result.get("symbol", normalized),
            currency=result.get("currency"),
            price=result.get("price"),
            change=result.get("change"),
            change_percent=result.get("change_percent"),
            previous_close=result.get("previous_close"),
            open=result.get("open"),
            day_high=result.get("day_high"),
            day_low=result.get("day_low"),
            volume=result.get("volume"),
            timestamp=result.get("timestamp"),
            error=result.get("error"),
        )
    except Exception as exc:
        return StockQuote(
            symbol=normalized,
            currency=None,
            price=None,
            change=None,
            change_percent=None,
            previous_close=None,
            open=None,
            day_high=None,
            day_low=None,
            volume=None,
            timestamp=_now_iso_utc8(),
            error=(
                "Failed to fetch quote via MCP: "
                f"{type(exc).__name__}: {exc}. "
                "Ensure the MCP yfinance server is running."
            ),
        )


@tool("search_news_with_duckduckgo")
def search_news_with_duckduckgo(query: str, limit: int = 5) -> List[NewsItem]:
    """Search recent news articles using DuckDuckGo for a given query string.

    This tool queries DuckDuckGo's news vertical to retrieve a small set of
    recent news articles that are relevant to a topic or security. It is
    suitable when the user asks for the latest news, headlines, or events
    related to a company, stock ticker, or macro theme.

    Typical usage patterns include questions such as:

    - \"What are the latest news about AAPL?\"
    - \"Show recent headlines for Tesla stock.\"
    - \"Any regulatory news about US banks this week?\"

    Args:
        query: Free-form search query describing the desired news. This can be
            a stock ticker such as ``\"AAPL\"``, a company name such as
            ``\"Apple Inc\"``, or a more detailed phrase like
            ``\"AAPL earnings\"``.
        limit: Maximum number of news results to return. The effective number
            of results may be smaller depending on what DuckDuckGo provides.

    Returns:
        A list of ``NewsItem`` dictionaries, where each element represents a
        single news article. For each item, the tool attempts to populate:

        - ``title``: Headline text.
        - ``url``: Article URL.
        - ``source``: Publisher or website name, if available.
        - ``published_time``: Publication date/time string from the source.
        - ``snippet``: Short summary or description of the article.

        If the search fails or no relevant results are found, this function
        returns an empty list rather than raising an exception.
    """

    query_normalized = query.strip()
    if not query_normalized:
        return []

    items: List[NewsItem] = []

    try:
        with DDGS() as ddgs:
            # ddgs.news expects the query as the first positional argument.
            results = ddgs.news(
                query_normalized,
                max_results=limit,
            )

            for entry in results:
                if not isinstance(entry, dict):
                    continue

                title = entry.get("title")
                url = entry.get("url") or entry.get("link")
                source = entry.get("source")
                published_time = entry.get("date") or entry.get("published")
                snippet = entry.get("excerpt") or entry.get("body")

                # Normalize published_time to UTC+8 when it looks like ISO8601.
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
                        # If the format is not ISO8601-compatible, keep original.
                        pass

                items.append(
                    NewsItem(
                        title=title,
                        url=url,
                        source=source,
                        published_time=published_time,
                        snippet=snippet,
                    )
                )
    except Exception:
        # For a tool used by an LLM, returning an empty list is safer than
        # propagating low-level network or parsing errors.
        return []

    return items


