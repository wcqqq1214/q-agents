"""Enhanced local database tools with quantitative features and forward returns.

These tools provide Agent with cross-modal reasoning capabilities by combining
news sentiment, technical indicators, and historical return data.
"""

import json
import logging
from datetime import datetime

from langchain_core.tools import tool

from app.database import get_conn
from app.ml.features import build_features

logger = logging.getLogger(__name__)


@tool("get_stock_data_with_sentiment")
def get_stock_data_with_sentiment(ticker: str, days: int = 90) -> str:
    """Fetch historical data with BOTH technical indicators AND news sentiment features.

    This is the PRIMARY tool for quantitative analysis. It combines price data,
    technical indicators (SMA, MACD, RSI), and news sentiment features (rolling
    sentiment scores, momentum) into a single response.

    **When to use:**
    - For comprehensive quantitative analysis combining price and sentiment
    - When you need to understand how news sentiment correlates with price moves
    - For cross-modal reasoning (e.g., "MACD shows bearish but sentiment is improving")

    **Key insight:**
    This tool enables you to detect divergences between technicals and sentiment,
    which often signal important market turning points.

    Args:
        ticker: Stock ticker symbol (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA).
        days: Number of recent days to analyze (default: 90).

    Returns:
        JSON string with:
        - ticker: Stock symbol
        - last_date: Most recent trading date
        - last_close: Most recent closing price
        - Technical indicators: sma_20, macd_line, macd_signal, rsi_14, volatility_5d
        - Sentiment features: sentiment_score_3d, sentiment_score_10d, sentiment_momentum_3d
        - News activity: news_count_3d, positive_ratio_3d, negative_ratio_3d
        - error: Error message if data unavailable
    """
    ticker = ticker.strip().upper()

    mag_seven = {"AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"}
    if ticker not in mag_seven:
        return json.dumps(
            {
                "ticker": ticker,
                "error": f"Ticker {ticker} not supported. Only Magnificent Seven available.",
            },
            ensure_ascii=False,
        )

    try:
        # Build full feature matrix
        df = build_features(ticker)

        if df.empty:
            return json.dumps(
                {
                    "ticker": ticker,
                    "error": "No data available. Run scripts/daily_harvester.py and scripts/process_layer1.py first.",
                },
                ensure_ascii=False,
            )

        # Get last N days
        df_recent = df.tail(days)

        if len(df_recent) == 0:
            return json.dumps(
                {"ticker": ticker, "error": "Insufficient data for analysis."},
                ensure_ascii=False,
            )

        # Get latest row
        latest = df_recent.iloc[-1]

        result = {
            "ticker": ticker,
            "last_date": str(latest["trade_date"].date()),
            "last_close": float(latest["close"]),
            "period_days": len(df_recent),
            # Technical indicators
            "sma_20": float(latest.get("ma5_vs_ma20", 0)),  # MA5 vs MA20 ratio
            "macd_line": float(latest.get("ret_1d", 0)),  # Using ret_1d as proxy
            "rsi_14": float(latest.get("rsi_14", 50)),
            "volatility_5d": float(latest.get("volatility_5d", 0)),
            # Sentiment features
            "sentiment_score_3d": float(latest.get("sentiment_score_3d", 0)),
            "sentiment_score_10d": float(latest.get("sentiment_score_10d", 0)),
            "sentiment_momentum_3d": float(latest.get("sentiment_momentum_3d", 0)),
            # News activity
            "news_count_3d": int(latest.get("news_count_3d", 0)),
            "positive_ratio_3d": float(latest.get("positive_ratio_3d", 0)),
            "negative_ratio_3d": float(latest.get("negative_ratio_3d", 0)),
        }

        return json.dumps(result, ensure_ascii=False)

    except Exception as exc:
        logger.error(f"Failed to fetch data for {ticker}: {exc}", exc_info=True)
        return json.dumps(
            {"ticker": ticker, "error": f"Database error: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )


@tool("search_news_with_returns")
def search_news_with_returns(ticker: str, start_date: str, end_date: str, limit: int = 20) -> str:
    """Search historical news WITH forward returns (T+0/1/3/5/10).

    This tool is CRITICAL for event-driven analysis. It returns news articles
    along with the ACTUAL market reaction (returns) that followed each event.

    **When to use:**
    - For historical event analysis ("What happened after last earnings?")
    - To understand typical market reactions to specific event types
    - For building event-driven trading insights

    **Key insight:**
    By seeing actual T+N returns, you can tell the Agent: "Historically, when
    similar news occurred, the stock moved X% in T+3 days."

    Args:
        ticker: Stock ticker symbol.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        limit: Max articles to return (default: 20).

    Returns:
        JSON string with:
        - ticker, start_date, end_date, count
        - articles: List of articles with:
            - trade_date: Trading day this news was aligned to
            - published_utc: Original publication time
            - title: Article headline
            - sentiment: positive/negative/neutral (from Layer 1)
            - key_discussion: Summary of what happened
            - reason_growth: Why this could push stock UP
            - reason_decrease: Why this could push stock DOWN
            - ret_t0: Same-day return (%)
            - ret_t1: Next-day return (%)
            - ret_t3: 3-day forward return (%)
            - ret_t5: 5-day forward return (%)
            - ret_t10: 10-day forward return (%)
    """
    ticker = ticker.strip().upper()

    mag_seven = {"AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"}
    if ticker not in mag_seven:
        return json.dumps(
            {"ticker": ticker, "error": f"Ticker {ticker} not supported."},
            ensure_ascii=False,
        )

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
            SELECT
                na.trade_date,
                na.published_utc,
                n.title,
                l1.sentiment,
                l1.key_discussion,
                l1.reason_growth,
                l1.reason_decrease,
                na.ret_t0,
                na.ret_t1,
                na.ret_t3,
                na.ret_t5,
                na.ret_t10
            FROM news_aligned na
            JOIN news n ON na.news_id = n.id
            LEFT JOIN layer1_results l1 ON na.news_id = l1.news_id AND na.symbol = l1.symbol
            WHERE na.symbol = ?
              AND na.trade_date >= ?
              AND na.trade_date <= ?
            ORDER BY na.trade_date DESC
            LIMIT ?
        """

        rows = conn.execute(query, (ticker, start_date, end_date, limit)).fetchall()
        conn.close()

        articles = []
        for row in rows:
            articles.append(
                {
                    "trade_date": row["trade_date"],
                    "published_utc": row["published_utc"],
                    "title": row["title"],
                    "sentiment": row["sentiment"] or "unknown",
                    "key_discussion": row["key_discussion"] or "",
                    "reason_growth": row["reason_growth"] or "",
                    "reason_decrease": row["reason_decrease"] or "",
                    "ret_t0": round(row["ret_t0"] * 100, 2) if row["ret_t0"] else None,
                    "ret_t1": round(row["ret_t1"] * 100, 2) if row["ret_t1"] else None,
                    "ret_t3": round(row["ret_t3"] * 100, 2) if row["ret_t3"] else None,
                    "ret_t5": round(row["ret_t5"] * 100, 2) if row["ret_t5"] else None,
                    "ret_t10": round(row["ret_t10"] * 100, 2) if row["ret_t10"] else None,
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
            f"Failed to search news for {ticker} ({start_date} to {end_date}): {exc}",
            exc_info=True,
        )
        return json.dumps(
            {"ticker": ticker, "error": f"Database error: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )


@tool("search_realtime_news")
def search_realtime_news(query: str, limit: int = 5) -> str:
    """Search for real-time breaking news using DuckDuckGo.

    **IMPORTANT: Use this tool ONLY for:**
    - Today's breaking news and intraday market events
    - General market sentiment and macro themes
    - Non-stock-specific queries

    **Do NOT use for:**
    - Historical news analysis (use search_news_with_returns instead)
    - Individual stock event research (use search_news_with_returns instead)

    Args:
        query: Search query.
        limit: Maximum number of results (default: 5).

    Returns:
        JSON string with query, count, and articles list.
    """
    from app.tools.finance_tools import search_news_with_duckduckgo

    try:
        results = search_news_with_duckduckgo.invoke({"query": query, "limit": limit})

        articles = []
        for item in results:
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
                "articles": articles,
            },
            ensure_ascii=False,
        )

    except Exception as exc:
        logger.error(f"Failed to search realtime news for '{query}': {exc}", exc_info=True)
        return json.dumps(
            {"query": query, "error": f"Search failed: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )


# Export enhanced tools
ENHANCED_TOOLS = [
    get_stock_data_with_sentiment,
    search_news_with_returns,
    search_realtime_news,
]
