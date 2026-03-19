"""Scheduled task to update OHLC data daily."""

import logging
from datetime import datetime, timedelta
from app.polygon.client import fetch_ohlc
from app.database import upsert_ohlc, update_metadata

logger = logging.getLogger(__name__)

SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']


def update_daily_ohlc():
    """Update all stocks with latest data (yesterday and today)."""
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    start_date = yesterday.isoformat()
    end_date = today.isoformat()

    logger.info(f"Starting daily OHLC update for {start_date} to {end_date}")

    success_count = 0
    total_records = 0

    for symbol in SYMBOLS:
        try:
            data = fetch_ohlc(symbol, start_date, end_date)
            if data:
                upsert_ohlc(symbol, data)
                update_metadata(symbol, start_date, end_date)
                total_records += len(data)
                success_count += 1
                logger.info(f"✓ Updated {symbol}: {len(data)} records")
            else:
                logger.warning(f"✗ No data returned for {symbol}")
        except Exception as e:
            logger.error(f"✗ Failed to update {symbol}: {e}")
            # Continue with other symbols

    logger.info(f"Daily update complete: {success_count}/{len(SYMBOLS)} stocks, {total_records} records")
