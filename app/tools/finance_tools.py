from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, TypedDict

import yfinance as yf
from langchain_core.tools import tool

from app.mcp_client.finance_client import (
    call_get_stock_data,
    call_get_us_stock_quote,
    call_search_news,
    call_search_news_tavily,
)

logger = logging.getLogger(__name__)


def _now_iso_utc8() -> str:
    """Return current time in ISO8601 format using UTC+8 timezone without microseconds."""

    return (
        datetime.now(timezone.utc)
        .astimezone(timezone(timedelta(hours=8)))
        .replace(microsecond=0)
        .isoformat()
    )


def _parse_news_published_time(raw: Optional[str]) -> Optional[datetime]:
    """Best-effort parse of a DuckDuckGo-style published_time string into UTC datetime.

    The incoming string can be one of:

    - An absolute date/time such as ``\"2025-03-10\"``, ``\"2025-03-10 14:30\"`` or
      an ISO8601-like representation.
    - A relative expression such as ``\"2 hours ago\"``, ``\"3 days ago\"`` or
      ``\"yesterday\"`` (case-insensitive).

    Returns:
        A timezone-aware ``datetime`` in UTC on successful parse; otherwise ``None``.
    """

    if not raw:
        return None

    text = raw.strip()
    if not text:
        return None

    now_utc = datetime.now(timezone.utc)
    lower = text.lower()

    # Handle simple relative expressions first.
    if "ago" in lower:
        parts = lower.split()
        # Expect a shape like: "<num> <unit> ago"
        try:
            if len(parts) >= 3 and parts[-1] == "ago":
                value = int(parts[0])
                unit = parts[1]
                if unit.startswith("hour"):
                    return now_utc - timedelta(hours=value)
                if unit.startswith("day"):
                    return now_utc - timedelta(days=value)
                if unit.startswith("week"):
                    return now_utc - timedelta(weeks=value)
        except Exception:
            return None

    if lower in {"yesterday"}:
        return now_utc - timedelta(days=1)

    # Try a series of absolute datetime formats.
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            # Assume naive values are UTC.
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    # Finally, try Python's ISO8601-style parser.
    try:
        dt2 = datetime.fromisoformat(text)
        if dt2.tzinfo is None:
            dt2 = dt2.replace(tzinfo=timezone.utc)
        return dt2.astimezone(timezone.utc)
    except Exception:
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
        fifty_two_week_high: 52-week high price if available.
        fifty_two_week_low: 52-week low price if available.
        market_cap: Market capitalization in same currency as listing (e.g. USD for US stocks).
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
    fifty_two_week_high: Optional[float]
    fifty_two_week_low: Optional[float]
    market_cap: Optional[float]
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
            fifty_two_week_high=None,
            fifty_two_week_low=None,
            market_cap=None,
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
            fifty_two_week_high=result.get("fifty_two_week_high"),
            fifty_two_week_low=result.get("fifty_two_week_low"),
            market_cap=result.get("market_cap"),
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
            fifty_two_week_high=None,
            fifty_two_week_low=None,
            market_cap=None,
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

    try:
        results = call_search_news(query_normalized, limit)
        return [
            NewsItem(
                title=r.get("title"),
                url=r.get("url"),
                source=r.get("source"),
                published_time=r.get("published_time"),
                snippet=r.get("snippet"),
            )
            for r in results
            if isinstance(r, dict)
        ]
    except Exception:
        return []


@tool("search_stock_news_with_yfinance")
def search_stock_news_with_yfinance(ticker: str, limit: int = 20) -> List[NewsItem]:
    """Search recent stock-specific news using ``yfinance.Ticker.news``.

    This tool queries Yahoo Finance news directly for a single stock ticker via
    :class:`yfinance.Ticker`. It is intended for cases where the agent already
    knows the exact symbol (for example, ``\"NVDA\"`` or ``\"AAPL\"``) and wants
    a clean, ticker-scoped news feed rather than a generic web search result.

    The function applies a **strict 7-day time window** based on the
    ``providerPublishTime`` field returned by Yahoo Finance. Only articles whose
    publication time can be parsed and falls within the last 7 days (in UTC)
    are included in the output. This makes the results suitable for
    short-horizon sentiment or event analysis.

    Args:
        ticker: Stock ticker symbol understood by Yahoo Finance (for example,
            ``\"NVDA\"``, ``\"AAPL\"``, or ``\"MSFT\"``). The value is
            normalized to upper case and passed to :class:`yfinance.Ticker`.
        limit: Maximum number of news items to return after filtering by the
            7-day window. The underlying Yahoo Finance API may return fewer
            items. Defaults to 20 so the agent has a richer event set for
            sentiment and macro analysis.

    Returns:
        A list of :class:`NewsItem` dictionaries, each representing a single
        article. For each item, this tool attempts to populate:

        - ``title``: Article headline from Yahoo Finance.
        - ``url``: Canonical article URL.
        - ``source``: Publisher name (for example, ``\"Reuters\"``).
        - ``published_time``: ISO8601 UTC timestamp derived from
          ``providerPublishTime``.
        - ``snippet``: Short summary if provided by Yahoo Finance; otherwise
          ``None``.

        If the ticker is empty, invalid, or an error occurs while calling the
        Yahoo backend, this function returns an empty list instead of raising.
    """

    normalized = (ticker or "").strip().upper()
    if not normalized:
        return []

    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=7)

    try:
        ticker_obj = yf.Ticker(normalized)
        raw_items = getattr(ticker_obj, "news", None) or []
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning(
            "search_stock_news_with_yfinance: failed to fetch news for %r: %s",
            normalized,
            exc,
            exc_info=True,
        )
        return []

    out: List[NewsItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        ts = item.get("providerPublishTime")
        try:
            if isinstance(ts, (int, float)):
                published_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                published_dt = None
        except Exception:
            published_dt = None

        if published_dt is None or published_dt < cutoff:
            continue

        out.append(
            NewsItem(
                title=item.get("title"),
                url=item.get("link"),
                source=item.get("publisher"),
                published_time=published_dt.isoformat().replace(microsecond=0),
                snippet=item.get("summary"),
            )
        )

        if len(out) >= limit:
            break

    return out


class StockDataSummary(TypedDict, total=False):
    """Structured summary returned by get_stock_data for LLM consumption.

    Attributes:
        ticker: Normalized ticker (e.g. NVDA, BTC-USD).
        error: Set when fetch or computation fails.
        last_close: Most recent adjusted close.
        sma_20: Simple moving average (20 periods) of close.
        macd_line: MACD line (EMA12 - EMA26).
        macd_signal: Signal line (EMA 9 of macd_line).
        macd_histogram: Histogram (macd_line - macd_signal).
        bb_middle: Bollinger middle band (SMA 20).
        bb_upper: Bollinger upper band.
        bb_lower: Bollinger lower band.
        period_rows: Number of rows in history series.
    """

    ticker: str
    error: str
    last_close: Optional[float]
    sma_20: Optional[float]
    macd_line: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]
    bb_middle: Optional[float]
    bb_upper: Optional[float]
    bb_lower: Optional[float]
    period_rows: int


@tool("get_stock_data")
def get_stock_data(ticker: str, period: str = "3mo") -> str:
    """Fetch historical OHLCV via yfinance and compute SMA and MACD-style indicators.

    Use this for quantitative/technical analysis only. Supports US equities and
    crypto pairs accepted by Yahoo (e.g. ``NVDA``, ``BTC-USD``). Returns a
    compact JSON string so the model can cite numbers without guessing.

    Args:
        ticker: Symbol such as ``NVDA``, ``AAPL``, or ``BTC-USD``.
        period: yfinance history period, default ``3mo`` (e.g. ``1mo``, ``6mo``, ``1y``).

    Returns:
        JSON string with keys including ``ticker``, ``last_close``, ``sma_20``,
        ``macd_line``, ``macd_signal``, ``macd_histogram``, ``bb_middle``,
        ``bb_upper``, ``bb_lower``, or ``error`` if
        data cannot be loaded.
    """

    normalized = (ticker or "").strip().upper()
    if not normalized:
        return json.dumps(
            StockDataSummary(ticker="", error="Empty ticker."),
            ensure_ascii=False,
        )

    try:
        result = call_get_stock_data(normalized, period)
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            StockDataSummary(
                ticker=normalized,
                error=f"{type(exc).__name__}: {exc}",
            ),
            ensure_ascii=False,
        )


@tool("search_financial_news")
def search_financial_news(query: str, limit: int = 5) -> List[NewsItem]:
    """Search financial news from roughly the last 7 days via DuckDuckGo.

    This tool uses the same backend as :func:`search_news_with_duckduckgo` but
    applies an additional time filter to only keep articles whose
    ``published_time`` can be parsed and falls within the past 7 days.

    Use for macro/sentiment research only. Pass ticker or company name or theme.

    Args:
        query: Search query (e.g. ticker, company name, or topic).
        limit: Max number of articles to return.

    Returns:
        List of NewsItem dicts (title, url, source, published_time, snippet).
    """
    query_normalized = query.strip()
    if not query_normalized:
        return []
    try:
        results = call_search_news(query_normalized, limit)
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=7)
        out: List[NewsItem] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            published_raw = r.get("published_time")
            published_dt = _parse_news_published_time(published_raw)
            # Strict policy: only keep items we can confidently place within the last 7 days.
            if published_dt is None or published_dt < cutoff:
                continue
            out.append(
                NewsItem(
                    title=r.get("title"),
                    url=r.get("url"),
                    source=r.get("source"),
                    published_time=published_raw,
                    snippet=r.get("snippet"),
                )
            )
        if not out and results is not None and len(results) == 0:
            logger.info(
                "search_financial_news: MCP returned empty list for query=%r",
                query_normalized,
            )
        return out
    except Exception as exc:
        logger.warning(
            "search_financial_news failed for query=%r: %s",
            query_normalized,
            exc,
            exc_info=True,
        )
        return []


@tool("search_news_with_tavily")
def search_news_with_tavily(query: str, limit: int = 5) -> List[NewsItem]:
    """Search recent news articles using Tavily API for a given query string.

    This tool queries Tavily's AI-optimized search API to retrieve high-quality
    news articles relevant to a topic or security. Tavily provides better
    content quality and relevance compared to generic search engines.

    Typical usage patterns include questions such as:

    - "What are the latest news about AAPL?"
    - "Show recent headlines for Tesla stock."
    - "Any regulatory news about US banks this week?"

    Args:
        query: Free-form search query describing the desired news. This can be
            a stock ticker such as ``"AAPL"``, a company name such as
            ``"Apple Inc"``, or a more detailed phrase like
            ``"AAPL earnings"``.
        limit: Maximum number of news results to return. The effective number
            of results may be smaller depending on what Tavily provides.

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

    try:
        results = call_search_news_tavily(query_normalized, limit)
        return [
            NewsItem(
                title=r.get("title"),
                url=r.get("url"),
                source=r.get("source"),
                published_time=r.get("published_time"),
                snippet=r.get("snippet"),
            )
            for r in results
            if isinstance(r, dict)
        ]
    except Exception:
        return []


@tool("search_financial_news_tavily")
def search_financial_news_tavily(query: str, limit: int = 5) -> List[NewsItem]:
    """Search financial news from roughly the last 7 days via Tavily API.

    This tool uses Tavily's AI-optimized search API and applies an additional
    time filter to only keep articles whose ``published_time`` can be parsed
    and falls within the past 7 days.

    Use for macro/sentiment research only. Pass ticker or company name or theme.

    Args:
        query: Search query (e.g. ticker, company name, or topic).
        limit: Max number of articles to return.

    Returns:
        List of NewsItem dicts (title, url, source, published_time, snippet).
    """
    query_normalized = query.strip()
    if not query_normalized:
        return []
    try:
        results = call_search_news_tavily(query_normalized, limit)
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=7)
        out: List[NewsItem] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            published_raw = r.get("published_time")
            published_dt = _parse_news_published_time(published_raw)
            # Strict policy: only keep items we can confidently place within the last 7 days.
            if published_dt is None or published_dt < cutoff:
                continue
            out.append(
                NewsItem(
                    title=r.get("title"),
                    url=r.get("url"),
                    source=r.get("source"),
                    published_time=published_raw,
                    snippet=r.get("snippet"),
                )
            )
        if not out and results is not None and len(results) == 0:
            logger.info(
                "search_financial_news_tavily: MCP returned empty list for query=%r",
                query_normalized,
            )
        return out
    except Exception as exc:
        logger.warning(
            "search_financial_news_tavily failed for query=%r: %s",
            query_normalized,
            exc,
            exc_info=True,
        )
        return []
