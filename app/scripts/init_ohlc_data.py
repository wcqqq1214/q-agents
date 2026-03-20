"""
Initialize OHLC database with 5 years of historical data.

Usage:
    uv run python -m app.scripts.init_ohlc_data
"""

import logging
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from app.database import init_db, upsert_ohlc, update_metadata, DEFAULT_DB_PATH
from app.mcp_client.finance_client import call_get_stock_history

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']


def main():
    logger.info("=" * 60)
    logger.info("Initializing OHLC database with 5 years of data")
    logger.info("=" * 60)

    # Initialize database
    init_db()
    logger.info("✓ Database initialized")

    # Calculate date range (5 years)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=5*365)

    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Symbols: {', '.join(SYMBOLS)}")
    logger.info("")

    total_records = 0
    success_count = 0

    for i, symbol in enumerate(SYMBOLS, 1):
        logger.info(f"[{i}/{len(SYMBOLS)}] Fetching {symbol}...")

        try:
            data = call_get_stock_history(symbol, start_date.isoformat(), end_date.isoformat())

            if data:
                upsert_ohlc(symbol, data)
                update_metadata(symbol, start_date.isoformat(), end_date.isoformat())
                total_records += len(data)
                success_count += 1
                logger.info(f"  ✓ {symbol}: {len(data)} records inserted")
            else:
                logger.warning(f"  ✗ {symbol}: No data returned from API")

            # Add rate limiting delay between symbols
            if i < len(SYMBOLS):
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"  ✗ {symbol}: Failed - {e}")
            continue

    logger.info("")
    logger.info("=" * 60)
    logger.info("Initialization complete!")
    logger.info(f"Success: {success_count}/{len(SYMBOLS)} stocks")
    logger.info(f"Total records: {total_records:,}")
    logger.info(f"Database: {DEFAULT_DB_PATH}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
