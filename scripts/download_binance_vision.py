"""Download historical crypto OHLC data from Binance Vision archive.

This script downloads monthly K-line data from Binance's public data archive
(data.binance.vision) and stores it in the SQLite database.

Usage:
    uv run python scripts/download_binance_vision.py
"""

import asyncio
import logging
import sys
import zipfile
import io
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
import requests
from tqdm import tqdm

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database.crypto_ohlc import update_crypto_metadata
from app.database.schema import init_db, get_conn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
BINANCE_VISION_BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]  # Binance uses no hyphen
INTERVALS = {
    "15m": "15m",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D",
    "1w": "1W",
    "1M": "1M"
    # Note: Binance doesn't have 1y interval, use 1M (monthly) instead
}
START_YEAR = 2020
# Download up to current month (don't download future months)
END_YEAR = datetime.now().year

# Binance K-line CSV columns (no header in files)
BINANCE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
]


def upsert_crypto_ohlc_batch(symbol: str, bar: str, records: List[Dict[str, Any]], batch_size: int = 10000) -> int:
    """Optimized batch insert for large datasets.

    Args:
        symbol: Cryptocurrency symbol
        bar: Timeframe bar
        records: List of OHLC records
        batch_size: Number of records per batch (default: 10000)

    Returns:
        Total number of records inserted
    """
    if not records:
        return 0

    conn = get_conn()
    total_inserted = 0

    try:
        # Disable auto-commit for better performance
        conn.execute("BEGIN TRANSACTION")

        query = """
            INSERT INTO crypto_ohlc (symbol, timestamp, date, open, high, low, close, volume, bar)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timestamp, bar) DO UPDATE SET
                date = excluded.date,
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume
        """

        # Process in batches with progress bar
        for i in tqdm(range(0, len(records), batch_size), desc="Inserting batches", unit="batch"):
            batch = records[i:i + batch_size]

            batch_data = [
                (
                    symbol,
                    record['timestamp'],
                    record['date'],
                    record['open'],
                    record['high'],
                    record['low'],
                    record['close'],
                    record['volume'],
                    bar
                )
                for record in batch
            ]

            conn.executemany(query, batch_data)
            total_inserted += len(batch)

        # Commit all changes at once
        conn.commit()

    except Exception as e:
        conn.rollback()
        logger.error(f"Error during batch insert: {e}")
        raise
    finally:
        conn.close()

    return total_inserted


def download_and_parse_kline(
    symbol: str,
    interval: str,
    year: int,
    month: int
) -> Optional[pd.DataFrame]:
    """Download and parse a single monthly K-line file from Binance Vision.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: K-line interval (e.g., '1m', '1h', '1d')
        year: Year (e.g., 2023)
        month: Month (1-12)

    Returns:
        DataFrame with parsed K-line data, or None if download fails
    """
    month_str = str(month).zfill(2)
    file_name = f"{symbol}-{interval}-{year}-{month_str}.zip"
    url = f"{BINANCE_VISION_BASE_URL}/{symbol}/{interval}/{file_name}"

    try:
        response = requests.get(url, timeout=30)

        if response.status_code == 404:
            logger.debug(f"File not found (404): {file_name}")
            return None

        if response.status_code != 200:
            logger.warning(f"Failed to download {file_name}: HTTP {response.status_code}")
            return None

        # Extract and parse CSV from zip
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                df = pd.read_csv(f, names=BINANCE_COLUMNS)

                # Convert timestamps from milliseconds to datetime
                df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
                df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')

                # Select and rename columns for our database
                df = df[[
                    'open_time', 'open', 'high', 'low', 'close', 'volume'
                ]].rename(columns={'open_time': 'timestamp'})

                return df

    except requests.exceptions.Timeout:
        logger.error(f"Timeout downloading {file_name}")
        return None
    except Exception as e:
        logger.error(f"Error processing {file_name}: {e}")
        return None


def generate_month_ranges(start_year: int, end_year: int) -> List[tuple]:
    """Generate list of (year, month) tuples for the date range.

    Args:
        start_year: Starting year
        end_year: Ending year (inclusive)

    Returns:
        List of (year, month) tuples
    """
    months = []
    current_date = datetime.now()

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            # Don't try to download future months
            if year == current_date.year and month > current_date.month:
                break
            months.append((year, month))

    return months


def download_symbol_interval(symbol: str, interval: str, bar_code: str) -> int:
    """Download all historical data for a symbol and interval.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Binance interval code (e.g., '1m', '1h')
        bar_code: Our internal bar code for database (e.g., '1m', '1H')

    Returns:
        Total number of records inserted
    """
    logger.info(f"Downloading {symbol} {interval} data...")

    months = generate_month_ranges(START_YEAR, END_YEAR)
    all_records = []

    # Use tqdm for progress bar
    for year, month in tqdm(months, desc=f"{symbol} {interval}", unit="month"):
        df = download_and_parse_kline(symbol, interval, year, month)

        if df is not None and not df.empty:
            all_records.append(df)

    if not all_records:
        logger.warning(f"No data downloaded for {symbol} {interval}")
        return 0

    logger.info(f"Combining {len(all_records)} monthly files...")

    # Combine all monthly data
    combined_df = pd.concat(all_records, ignore_index=True)

    # Sort by timestamp
    combined_df = combined_df.sort_values('timestamp')

    # Remove duplicates (in case of overlapping data)
    combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='first')

    logger.info(f"Processing {len(combined_df):,} records...")

    # Convert to database format
    db_symbol = symbol[:3] + "-" + symbol[3:]  # BTCUSDT -> BTC-USDT
    records = []

    for idx, row in combined_df.iterrows():
        try:
            # Convert pandas Timestamp to Python datetime to avoid overflow issues
            dt = row['timestamp'].to_pydatetime()
            timestamp_ms = int(dt.timestamp() * 1000)

            records.append({
                "timestamp": timestamp_ms,
                "date": dt.isoformat(),
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": float(row['volume'])
            })
        except (ValueError, OverflowError) as e:
            # Skip records with invalid timestamps (e.g., year > 9999)
            logger.warning(f"Skipping record {idx} with invalid timestamp: {row['timestamp']} - {e}")
            continue

    # Batch insert to database with progress
    logger.info(f"Inserting {len(records):,} records into database...")
    count = upsert_crypto_ohlc_batch(db_symbol, bar_code, records)

    # Update metadata
    if records:
        start_date = records[0]["date"]
        end_date = records[-1]["date"]
        update_crypto_metadata(
            symbol=db_symbol,
            bar=bar_code,
            start=start_date,
            end=end_date,
            total_records=count
        )
        logger.info(f"✓ {db_symbol} {bar_code}: {count:,} records ({start_date[:10]} to {end_date[:10]})")

    return count


def main():
    """Main download function."""
    logger.info("=" * 70)
    logger.info("Binance Vision Historical Data Download")
    logger.info("=" * 70)
    logger.info(f"Symbols: {', '.join(SYMBOLS)}")
    logger.info(f"Intervals: {', '.join(INTERVALS.keys())}")
    logger.info(f"Date range: {START_YEAR}-01 to {END_YEAR}-{datetime.now().month:02d}")
    logger.info("")

    # Initialize database
    init_db()
    logger.info("✓ Database initialized")
    logger.info("")

    total_records = 0
    total_tasks = len(SYMBOLS) * len(INTERVALS)
    completed = 0

    for symbol in SYMBOLS:
        for binance_interval, bar_code in INTERVALS.items():
            count = download_symbol_interval(symbol, binance_interval, bar_code)
            total_records += count
            completed += 1

            logger.info(f"Progress: {completed}/{total_tasks} tasks completed")
            logger.info("")

    logger.info("=" * 70)
    logger.info("Download Complete!")
    logger.info(f"Total records inserted: {total_records:,}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
