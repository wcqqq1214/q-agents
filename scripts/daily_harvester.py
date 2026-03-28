"""Daily data harvester for Magnificent Seven stocks.

This script fetches OHLC and news data from Polygon API and stores it in SQLite.
It implements strict rate limiting (5 requests/minute) and incremental updates.
After fetching, it automatically runs the alignment and Layer 0 pipeline.

Usage:
    python scripts/daily_harvester.py [--full]

    --full: Fetch all historical data (2 years) instead of incremental update
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from app.database import get_conn, init_db
from app.pipeline import align_news_for_symbol, run_layer0
from app.polygon import fetch_news, fetch_ohlc

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Magnificent Seven tickers
MAGNIFICENT_SEVEN = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]

# Date range for full fetch (2 years)
TODAY = datetime.now(timezone.utc).date().isoformat()
TWO_YEARS_AGO = (datetime.now(timezone.utc).date() - timedelta(days=2 * 365)).isoformat()


def get_last_fetch_dates(symbol: str) -> Tuple[str, str]:
    """Get the last OHLC and news fetch dates for a ticker.

    Args:
        symbol: Stock ticker symbol.

    Returns:
        Tuple of (last_ohlc_fetch, last_news_fetch) as ISO date strings.
        Returns (TWO_YEARS_AGO, TWO_YEARS_AGO) if never fetched.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT last_ohlc_fetch, last_news_fetch FROM tickers WHERE symbol = ?",
            (symbol,),
        ).fetchone()

        if not row:
            return TWO_YEARS_AGO, TWO_YEARS_AGO

        last_ohlc = row["last_ohlc_fetch"] or TWO_YEARS_AGO
        last_news = row["last_news_fetch"] or TWO_YEARS_AGO

        return last_ohlc, last_news
    finally:
        conn.close()


def store_ohlc_data(symbol: str, rows: List[dict]) -> int:
    """Store OHLC data in the database.

    Args:
        symbol: Stock ticker symbol.
        rows: List of OHLC data dictionaries.

    Returns:
        Number of rows inserted.
    """
    if not rows:
        return 0

    conn = get_conn()
    try:
        before_count = conn.execute(
            "SELECT COUNT(*) FROM ohlc WHERE symbol = ?", (symbol,)
        ).fetchone()[0]

        for row in rows:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO ohlc
                       (symbol, date, open, high, low, close, volume)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        symbol,
                        row["date"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                    ),
                )
            except Exception as exc:
                logger.error(f"Failed to insert OHLC row for {symbol}: {exc}")

        # Update last fetch timestamp
        conn.execute(
            "UPDATE tickers SET last_ohlc_fetch = ? WHERE symbol = ?",
            (TODAY, symbol),
        )

        conn.commit()
        after_count = conn.execute(
            "SELECT COUNT(*) FROM ohlc WHERE symbol = ?", (symbol,)
        ).fetchone()[0]
        inserted = after_count - before_count
        return inserted
    except Exception as exc:
        logger.error(f"Failed to store OHLC data for {symbol}: {exc}")
        conn.rollback()
        return 0
    finally:
        conn.close()


def store_news_data(symbol: str, articles: List[dict]) -> int:
    """Store news articles in the database.

    Args:
        symbol: Stock ticker symbol.
        articles: List of news article dictionaries.

    Returns:
        Number of articles inserted.
    """
    if not articles:
        return 0

    conn = get_conn()
    try:
        before_count = conn.execute(
            "SELECT COUNT(*) FROM news WHERE symbol = ?", (symbol,)
        ).fetchone()[0]

        for article in articles:
            article_id = article.get("id")
            if not article_id:
                continue

            try:
                conn.execute(
                    """INSERT OR IGNORE INTO news
                       (id, symbol, published_utc, title, description, article_url, publisher)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        article_id,
                        symbol,
                        article["published_utc"],
                        article["title"],
                        article["description"],
                        article["article_url"],
                        article["publisher"],
                    ),
                )
            except Exception as exc:
                logger.error(f"Failed to insert news article {article_id}: {exc}")

        # Update last fetch timestamp
        conn.execute(
            "UPDATE tickers SET last_news_fetch = ? WHERE symbol = ?",
            (TODAY, symbol),
        )

        conn.commit()
        after_count = conn.execute(
            "SELECT COUNT(*) FROM news WHERE symbol = ?", (symbol,)
        ).fetchone()[0]
        inserted = after_count - before_count
        return inserted
    except Exception as exc:
        logger.error(f"Failed to store news data for {symbol}: {exc}")
        conn.rollback()
        return 0
    finally:
        conn.close()


def harvest_ticker(symbol: str, full_fetch: bool = False) -> None:
    """Harvest OHLC and news data for a single ticker.

    Args:
        symbol: Stock ticker symbol.
        full_fetch: If True, fetch all historical data. If False, incremental update.
    """
    logger.info(f"{'=' * 60}")
    logger.info(f"Processing {symbol}")
    logger.info(f"{'=' * 60}")

    # Determine date range
    if full_fetch:
        ohlc_start = TWO_YEARS_AGO
        news_start = TWO_YEARS_AGO
        logger.info(f"Full fetch mode: {TWO_YEARS_AGO} to {TODAY}")
    else:
        last_ohlc, last_news = get_last_fetch_dates(symbol)

        # Start from day after last fetch
        ohlc_start = (datetime.fromisoformat(last_ohlc) + timedelta(days=1)).date().isoformat()
        news_start = (datetime.fromisoformat(last_news) + timedelta(days=1)).date().isoformat()

        logger.info("Incremental update:")
        logger.info(f"  OHLC: {ohlc_start} to {TODAY}")
        logger.info(f"  News: {news_start} to {TODAY}")

        # Skip if already up to date
        if ohlc_start > TODAY and news_start > TODAY:
            logger.info("Already up to date. Skipping.")
            return

    # Fetch and store OHLC data
    try:
        if ohlc_start <= TODAY:
            ohlc_rows = fetch_ohlc(symbol, ohlc_start, TODAY)
            inserted_ohlc = store_ohlc_data(symbol, ohlc_rows)
            logger.info(f"OHLC: Fetched {len(ohlc_rows)}, inserted {inserted_ohlc} rows")
        else:
            logger.info("OHLC: Already up to date")
    except Exception as exc:
        logger.error(f"OHLC fetch failed for {symbol}: {exc}")

    # Fetch and store news data
    try:
        if news_start <= TODAY:
            news_articles = fetch_news(symbol, news_start, TODAY)
            inserted_news = store_news_data(symbol, news_articles)
            logger.info(f"News: Fetched {len(news_articles)}, inserted {inserted_news} articles")
        else:
            logger.info("News: Already up to date")
    except Exception as exc:
        logger.error(f"News fetch failed for {symbol}: {exc}")

    # Run pipeline: alignment + layer0
    logger.info("Running pipeline...")
    try:
        align_result = align_news_for_symbol(symbol)
        logger.info(f"  Alignment: {align_result.get('aligned', 0)} news aligned")

        layer0_result = run_layer0(symbol)
        logger.info(f"  Layer 0: {layer0_result['passed']}/{layer0_result['total']} passed filter")
    except Exception as exc:
        logger.error(f"Pipeline failed for {symbol}: {exc}")

    logger.info("")


def main() -> None:
    """Main entry point for the daily harvester."""
    parser = argparse.ArgumentParser(
        description="Harvest OHLC and news data for Magnificent Seven stocks"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Fetch all historical data (2 years) instead of incremental update",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Daily Data Harvester - Magnificent Seven")
    logger.info("=" * 60)
    logger.info(f"Mode: {'FULL FETCH' if args.full else 'INCREMENTAL UPDATE'}")
    logger.info(f"Date: {TODAY}")
    logger.info(f"Tickers: {', '.join(MAGNIFICENT_SEVEN)}")
    logger.info("Rate limit: 5 requests/minute (Polygon free tier)")
    logger.info("=" * 60)
    logger.info("")

    # Initialize database
    init_db()

    # Process each ticker
    total_start = datetime.now()

    for idx, symbol in enumerate(MAGNIFICENT_SEVEN, 1):
        logger.info(f"[{idx}/{len(MAGNIFICENT_SEVEN)}] {symbol}")
        try:
            harvest_ticker(symbol, full_fetch=args.full)
        except Exception as exc:
            logger.error(f"Failed to process {symbol}: {exc}", exc_info=True)

    # Summary
    total_elapsed = (datetime.now() - total_start).total_seconds()
    logger.info("=" * 60)
    logger.info("HARVEST COMPLETE")
    logger.info(f"Total time: {total_elapsed:.1f}s")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Run Layer 1 semantic extraction:")
    logger.info("     python scripts/process_layer1.py")
    logger.info("  2. Build feature matrix:")
    logger.info(
        "     python -c 'from app.ml.features import build_features; build_features(\"NVDA\")'"
    )


if __name__ == "__main__":
    main()
