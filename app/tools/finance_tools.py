from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, TypedDict

import yfinance as yf
from ddgs import DDGS
from langchain_core.tools import tool


def _now_iso_utc8() -> str:
    """Return current time in ISO8601 format using UTC+8 timezone without microseconds."""

    return (
        datetime.now(timezone.utc)
        .astimezone(timezone(timedelta(hours=8)))
        .replace(microsecond=0)
        .isoformat()
    )


def _round_or_none(value: Optional[float], ndigits: int = 3) -> Optional[float]:
    """Round a float to the given number of digits if not None."""

    if value is None:
        return None
    try:
        return round(value, ndigits)
    except (TypeError, ValueError):
        return None


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

    quote: StockQuote = StockQuote(
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
        timestamp=None,
    )

    try:
        yf_ticker = yf.Ticker(normalized)

        fast_info: Any = getattr(yf_ticker, "fast_info", None)

        # Try to get daily OHLC data for more reliable open / previous_close.
        history = yf_ticker.history(period="2d", interval="1d", auto_adjust=False)
        if not history.empty:
            # Latest row: today's candle (or most recent trading day)
            latest = history.iloc[-1]
            day_high = float(latest.get("High")) if "High" in latest else None
            day_low = float(latest.get("Low")) if "Low" in latest else None
            # Use the last close as a more stable "price" snapshot
            price = float(latest.get("Close")) if "Close" in latest else None

            # Previous row (if exists): previous day's close as previous_close
            if len(history.index) > 1:
                prev = history.iloc[-2]
                previous_close = (
                    float(prev.get("Close")) if "Close" in prev else previous_close
                )

        def _get_fast(field_name: str, attr_name: str) -> Optional[float]:
            if fast_info is None:
                return None
            if hasattr(fast_info, attr_name):
                value = getattr(fast_info, attr_name)
            elif isinstance(fast_info, dict):
                value = fast_info.get(field_name)
            else:
                value = None
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        # If daily history did not provide values, fall back to fast_info.
        if "price" not in locals() or price is None:
            price = _get_fast("lastPrice", "last_price")
        if "previous_close" not in locals() or previous_close is None:
            previous_close = _get_fast("previousClose", "previous_close")
        if "open_price" not in locals() or open_price is None:
            open_price = _get_fast("open", "open")
        if "day_high" not in locals() or day_high is None:
            day_high = _get_fast("dayHigh", "day_high")
        if "day_low" not in locals() or day_low is None:
            day_low = _get_fast("dayLow", "day_low")
        # Prefer today's daily volume from history; fall back to fast_info.
        if not history.empty and "Volume" in latest:
            volume = float(latest.get("Volume"))
        else:
            volume = _get_fast("lastVolume", "last_volume")

        currency: Optional[str] = None
        if fast_info is not None:
            if hasattr(fast_info, "currency"):
                currency = getattr(fast_info, "currency")
            elif isinstance(fast_info, dict):
                currency = fast_info.get("currency")

        change: Optional[float] = None
        change_percent: Optional[float] = None
        if price is not None and previous_close not in (None, 0):
            change = price - previous_close  # type: ignore[operator]
            try:
                change_percent = (change / previous_close) * 100  # type: ignore[operator]
            except TypeError:
                change_percent = None

        # Round selected numeric fields: price-related to 3 decimals, percent to 2
        price = _round_or_none(price, 3)
        previous_close = _round_or_none(previous_close, 3)
        open_price = _round_or_none(open_price, 3)
        day_high = _round_or_none(day_high, 3)
        day_low = _round_or_none(day_low, 3)
        change = _round_or_none(change, 3)
        change_percent = _round_or_none(change_percent, 2)
        if volume is not None:
            try:
                volume = int(volume)
            except (TypeError, ValueError):
                volume = None

        quote.update(
            {
                "currency": currency,
                "price": price,
                "previous_close": previous_close,
                "open": open_price,
                "day_high": day_high,
                "day_low": day_low,
                "volume": volume,
                "change": change,
                "change_percent": change_percent,
                "timestamp": _now_iso_utc8(),
            },
        )

        if (
            quote["price"] is None
            and quote.get("previous_close") is None
            and quote.get("open") is None
        ):
            quote["error"] = (
                "No quote data available for the specified ticker. "
                "The symbol may be invalid or data may be temporarily unavailable."
            )

    except Exception as exc:
        quote["error"] = (
            "Failed to fetch quote data from Yahoo Finance: "
            f"{type(exc).__name__}: {exc}"
        )
        quote["timestamp"] = _now_iso_utc8()

    return quote


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


