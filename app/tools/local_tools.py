"""Local database tools for querying historical stock data and news.

These tools query the local SQLite database instead of making external API calls,
providing fast access to historical data for the Magnificent Seven stocks.
"""

import json
import logging
from datetime import datetime

import pandas as pd
from langchain_core.tools import tool

from app.database import get_conn

logger = logging.getLogger(__name__)


@tool("get_local_stock_data")
def get_local_stock_data(ticker: str, days: int = 90) -> str:
    """Fetch historical OHLC data from local database and compute technical indicators.

    This tool queries the local SQLite database for historical price data and
    calculates SMA (Simple Moving Average) and MACD indicators. Use this for
    quantitative/technical analysis of the Magnificent Seven stocks.

    **When to use:**
    - For historical price analysis and technical indicators
    - When analyzing trends over weeks or months
    - For backtesting or pattern recognition

    **Do NOT use for:**
    - Real-time or intraday quotes (data may be 1 day delayed)
    - Stocks outside the Magnificent Seven (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA)

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "NVDA", "TSLA").
                Must be one of the Magnificent Seven.
        days: Number of days of historical data to retrieve (default: 90).
              Minimum 30 days recommended for meaningful technical indicators.

    Returns:
        JSON string containing:
        - ticker: The stock symbol
        - period_rows: Number of data points retrieved
        - last_date: Most recent trading date in dataset
        - last_close: Most recent closing price
        - sma_20: 20-day simple moving average
        - macd_line: MACD line (12-day EMA - 26-day EMA)
        - macd_signal: MACD signal line (9-day EMA of MACD)
        - macd_histogram: MACD histogram (MACD line - signal line)
        - bb_middle: Bollinger Band middle (same as SMA 20)
        - bb_upper: Bollinger Band upper (middle + 2 * std dev)
        - bb_lower: Bollinger Band lower (middle - 2 * std dev)
        - price_change_pct: Percentage change over the period
        - error: Error message if data cannot be retrieved

    Example:
        >>> result = get_local_stock_data.invoke({"ticker": "NVDA", "days": 60})
        >>> data = json.loads(result)
        >>> print(f"NVDA last close: ${data['last_close']:.2f}")
    """
    ticker = ticker.strip().upper()

    # Validate ticker
    mag_seven = {"AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"}
    if ticker not in mag_seven:
        return json.dumps(
            {
                "ticker": ticker,
                "error": f"Ticker {ticker} not supported. Only Magnificent Seven stocks are available: {', '.join(sorted(mag_seven))}",
            },
            ensure_ascii=False,
        )

    try:
        conn = get_conn()

        # Query OHLC data
        query = """
            SELECT date, open, high, low, close, volume
            FROM ohlc
            WHERE symbol = ?
            ORDER BY date DESC
            LIMIT ?
        """
        rows = conn.execute(query, (ticker, days)).fetchall()
        conn.close()

        if not rows:
            return json.dumps(
                {
                    "ticker": ticker,
                    "error": f"No data found for {ticker}. Run scripts/daily_harvester.py to fetch data.",
                },
                ensure_ascii=False,
            )

        # Convert to DataFrame (reverse to chronological order)
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df = df.iloc[::-1].reset_index(drop=True)
        df["close"] = pd.to_numeric(df["close"])

        # Calculate technical indicators
        # SMA 20
        sma_20 = df["close"].rolling(window=20, min_periods=1).mean().iloc[-1]

        # Bollinger Bands (20, 2)
        bb_middle = sma_20  # Same as SMA 20
        bb_std = df["close"].rolling(window=20, min_periods=1).std().iloc[-1]
        bb_upper = bb_middle + (2 * bb_std)
        bb_lower = bb_middle - (2 * bb_std)

        # MACD (12, 26, 9)
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_histogram = macd_line - macd_signal

        # Price change
        first_close = df["close"].iloc[0]
        last_close = df["close"].iloc[-1]
        price_change_pct = ((last_close - first_close) / first_close) * 100

        result = {
            "ticker": ticker,
            "period_rows": len(df),
            "last_date": df["date"].iloc[-1],
            "last_close": float(last_close),
            "sma_20": float(sma_20),
            "macd_line": float(macd_line.iloc[-1]),
            "macd_signal": float(macd_signal.iloc[-1]),
            "macd_histogram": float(macd_histogram.iloc[-1]),
            "bb_middle": float(bb_middle),
            "bb_upper": float(bb_upper),
            "bb_lower": float(bb_lower),
            "price_change_pct": float(price_change_pct),
        }

        return json.dumps(result, ensure_ascii=False)

    except Exception as exc:
        logger.error(f"Failed to fetch local stock data for {ticker}: {exc}", exc_info=True)
        return json.dumps(
            {"ticker": ticker, "error": f"Database error: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )


@tool("search_local_historical_news")
def search_local_historical_news(
    ticker: str, start_date: str, end_date: str, limit: int = 20
) -> str:
    """Search historical news articles from local database for a specific time period.

    This tool queries the local SQLite database for news articles within a date range.
    Use this for deep historical analysis, event correlation, and backtesting.

    **When to use:**
    - Analyzing historical events and their market impact
    - Correlating news with price movements
    - Building event-driven analysis or RAG memory
    - Researching past earnings, product launches, or regulatory events

    **Do NOT use for:**
    - Today's breaking news (use search_realtime_news instead)
    - General market sentiment (use search_realtime_news instead)
    - Stocks outside the Magnificent Seven

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "META").
                Must be one of the Magnificent Seven.
        start_date: Start date in YYYY-MM-DD format (e.g., "2024-01-01").
        end_date: End date in YYYY-MM-DD format (e.g., "2024-03-31").
        limit: Maximum number of articles to return (default: 20, max: 100).

    Returns:
        JSON string containing:
        - ticker: The stock symbol
        - start_date: Query start date
        - end_date: Query end date
        - count: Number of articles found
        - articles: List of article objects with:
            - published_utc: Publication timestamp
            - title: Article headline
            - description: Article summary/snippet
            - publisher: News source
            - article_url: Link to full article
        - error: Error message if query fails

    Example:
        >>> result = search_local_historical_news.invoke({
        ...     "ticker": "TSLA",
        ...     "start_date": "2024-01-01",
        ...     "end_date": "2024-01-31",
        ...     "limit": 10
        ... })
        >>> data = json.loads(result)
        >>> for article in data["articles"]:
        ...     print(f"{article['published_utc']}: {article['title']}")
    """
    ticker = ticker.strip().upper()
    limit = min(limit, 100)  # Cap at 100

    # Validate ticker
    mag_seven = {"AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"}
    if ticker not in mag_seven:
        return json.dumps(
            {
                "ticker": ticker,
                "error": f"Ticker {ticker} not supported. Only Magnificent Seven stocks are available.",
            },
            ensure_ascii=False,
        )

    # Validate dates
    try:
        datetime.fromisoformat(start_date)
        datetime.fromisoformat(end_date)
    except ValueError as exc:
        return json.dumps(
            {
                "ticker": ticker,
                "error": f"Invalid date format. Use YYYY-MM-DD. Error: {exc}",
            },
            ensure_ascii=False,
        )

    try:
        conn = get_conn()

        query = """
            SELECT published_utc, title, description, publisher, article_url
            FROM news
            WHERE symbol = ?
              AND published_utc >= ?
              AND published_utc <= ?
            ORDER BY published_utc DESC
            LIMIT ?
        """

        rows = conn.execute(query, (ticker, start_date, end_date, limit)).fetchall()
        conn.close()

        articles = []
        for row in rows:
            articles.append(
                {
                    "published_utc": row["published_utc"],
                    "title": row["title"],
                    "description": row["description"],
                    "publisher": row["publisher"],
                    "article_url": row["article_url"],
                }
            )

        result = {
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "count": len(articles),
            "articles": articles,
        }

        return json.dumps(result, ensure_ascii=False)

    except Exception as exc:
        logger.error(
            f"Failed to search local news for {ticker} ({start_date} to {end_date}): {exc}",
            exc_info=True,
        )
        return json.dumps(
            {"ticker": ticker, "error": f"Database error: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )


@tool("search_realtime_news")
def search_realtime_news(query: str, limit: int = 5) -> str:
    """Search for real-time breaking news via MCP server with automatic fallback.

    **Search Strategy (via MCP server):**
    1. Tries Tavily first (higher quality, AI-optimized results)
    2. Falls back to DuckDuckGo if Tavily fails or returns no results
    3. Returns error only if both sources fail

    **IMPORTANT: Use this tool ONLY for:**
    - Today's breaking news and intraday market events
    - General market sentiment and macro themes (e.g., "Fed rate decision", "tech sector")
    - Non-stock-specific queries (e.g., "AI regulation", "semiconductor shortage")

    **Do NOT use for:**
    - Historical news analysis (use search_local_historical_news instead)
    - Individual stock event research (use search_local_historical_news instead)
    - Anything older than today

    This tool makes external API calls via MCP server and should be used sparingly.
    For historical analysis of the Magnificent Seven stocks, always prefer search_local_historical_news.

    Args:
        query: Search query (e.g., "NVDA earnings today", "Fed interest rate decision").
        limit: Maximum number of results (default: 5).

    Returns:
        JSON string containing:
        - query: The search query
        - count: Number of results
        - source: Which source was used ("tavily" or "duckduckgo")
        - articles: List of news articles with title, url, source, snippet
        - error: Error message if both searches fail
    """
    from app.mcp_client.finance_client import call_search_news, call_search_news_tavily

    # Try Tavily first (via MCP)
    try:
        tavily_results = call_search_news_tavily(query, limit)

        if tavily_results:  # If Tavily returns results, use them
            articles = []
            for item in tavily_results:
                articles.append(
                    {
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "source": item.get("source"),
                        "published_time": item.get("published_time"),
                        "snippet": item.get("snippet"),
                    }
                )

            return json.dumps(
                {
                    "query": query,
                    "count": len(articles),
                    "source": "tavily",
                    "articles": articles,
                },
                ensure_ascii=False,
            )
        else:
            logger.info(f"Tavily returned no results for '{query}', falling back to DuckDuckGo")
    except Exception as exc:
        logger.warning(f"Tavily search failed for '{query}': {exc}, falling back to DuckDuckGo")

    # Fallback to DuckDuckGo (via MCP)
    try:
        ddg_results = call_search_news(query, limit)

        articles = []
        for item in ddg_results:
            articles.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "source": item.get("source"),
                    "published_time": item.get("published_time"),
                    "snippet": item.get("snippet"),
                }
            )

        return json.dumps(
            {
                "query": query,
                "count": len(articles),
                "source": "duckduckgo",
                "articles": articles,
            },
            ensure_ascii=False,
        )

    except Exception as exc:
        logger.error(f"Both Tavily and DuckDuckGo failed for '{query}': {exc}", exc_info=True)
        return json.dumps(
            {
                "query": query,
                "error": f"Both search sources failed. Last error: {type(exc).__name__}: {exc}",
            },
            ensure_ascii=False,
        )


# Export tools for use in Agent
LOCAL_TOOLS = [
    get_local_stock_data,
    search_local_historical_news,
    search_realtime_news,
]
