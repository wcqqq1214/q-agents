"""Quick test script to verify Binance Vision download works.

Downloads a single month of data to test the pipeline.

Usage:
    uv run python scripts/test_binance_download.py
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.download_binance_vision import download_and_parse_kline, upsert_crypto_ohlc_batch
from app.database.crypto_ohlc import get_crypto_metadata
from app.database.schema import init_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_download():
    """Test downloading a single month of data."""
    logger.info("Testing Binance Vision download with optimized batch insert...")

    # Initialize database
    init_db()

    # Test download: BTC 1-hour data for January 2024
    symbol = "BTCUSDT"
    interval = "1h"
    year = 2024
    month = 1

    logger.info(f"Downloading {symbol} {interval} for {year}-{month:02d}...")
    df = download_and_parse_kline(symbol, interval, year, month)

    if df is None or df.empty:
        logger.error("❌ Download failed or returned no data")
        return False

    logger.info(f"✓ Downloaded {len(df)} records")
    logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    logger.info(f"Sample data:\n{df.head()}")

    # Test optimized database insertion
    db_symbol = "BTC-USDT"
    records = []

    for _, row in df.iterrows():
        timestamp_ms = int(row['timestamp'].timestamp() * 1000)
        records.append({
            "timestamp": timestamp_ms,
            "date": row['timestamp'].isoformat(),
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close']),
            "volume": float(row['volume'])
        })

    logger.info(f"Testing optimized batch insert with {len(records)} records...")
    count = upsert_crypto_ohlc_batch(db_symbol, interval, records, batch_size=100)
    logger.info(f"✓ Inserted {count} records into database")

    # Verify metadata
    metadata = get_crypto_metadata(db_symbol, interval)
    if metadata:
        logger.info(f"✓ Metadata: {metadata}")

    logger.info("✅ Test completed successfully!")
    return True

if __name__ == "__main__":
    success = test_download()
    sys.exit(0 if success else 1)
