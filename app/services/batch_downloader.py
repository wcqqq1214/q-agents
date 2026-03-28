"""Batch downloader for Binance Vision historical data."""

import csv
import io
import logging
import zipfile
from datetime import date, datetime, timezone
from typing import Any, Dict, List

import httpx

from app.database.crypto_ohlc import upsert_crypto_ohlc

logger = logging.getLogger(__name__)

BINANCE_VISION_BASE = "https://data.binance.vision/data/spot/daily/klines"

# Binance Vision changed timestamp format on 2025-01-01
# Before: milliseconds (13 digits)
# After: microseconds (16 digits)
TIMESTAMP_FORMAT_CHANGE_DATE = date(2025, 1, 1)


def get_download_url(symbol: str, interval: str, target_date: date) -> str:
    """
    Generate Binance Vision download URL for a specific date.

    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        interval: K-line interval (e.g., "1m", "1d")
        target_date: Date to download

    Returns:
        Download URL string
    """
    date_str = target_date.strftime("%Y-%m-%d")
    filename = f"{symbol}-{interval}-{date_str}.zip"
    return f"{BINANCE_VISION_BASE}/{symbol}/{interval}/{filename}"


async def download_daily_data(
    symbol: str, interval: str, target_date: date
) -> List[Dict[str, Any]]:
    """
    Download and parse daily K-line data from Binance Vision.

    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        interval: K-line interval (e.g., "1m", "1d")
        target_date: Date to download

    Returns:
        List of parsed K-line dictionaries with keys:
        timestamp, date, open, high, low, close, volume

    Note:
        Binance Vision changed timestamp format on 2025-01-01:
        - Before 2025-01-01: milliseconds (13 digits)
        - From 2025-01-01: microseconds (16 digits)
        Returns empty list if data is not available (404) or on error.
    """
    url = get_download_url(symbol, interval, target_date)
    logger.info(f"Downloading {symbol} {interval} for {target_date} from {url}")

    # Determine expected timestamp format based on date
    use_microseconds = target_date >= TIMESTAMP_FORMAT_CHANGE_DATE

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()

        # Extract CSV from ZIP
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            csv_filename = zip_file.namelist()[0]
            csv_content = zip_file.read(csv_filename).decode("utf-8")

        # Parse CSV
        result = []
        reader = csv.reader(io.StringIO(csv_content))
        for row_num, row in enumerate(reader, 1):
            if not row or len(row) < 6:
                continue

            try:
                timestamp_raw = int(row[0])

                # Convert timestamp based on expected format
                if use_microseconds:
                    # Data from 2025-01-01 onwards: microseconds format
                    # Verify it's actually in microseconds (16 digits)
                    if timestamp_raw > 10**15:
                        timestamp_ms = timestamp_raw // 1000
                    else:
                        # Fallback: might be milliseconds
                        timestamp_ms = timestamp_raw
                        logger.warning(
                            f"Expected microseconds but got milliseconds for {target_date} row {row_num}"
                        )
                else:
                    # Data before 2025-01-01: milliseconds format
                    # Verify it's actually in milliseconds (13 digits)
                    if timestamp_raw > 10**15:
                        # Unexpected: got microseconds when expecting milliseconds
                        timestamp_ms = timestamp_raw // 1000
                        logger.warning(
                            f"Expected milliseconds but got microseconds for {target_date} row {row_num}"
                        )
                    else:
                        timestamp_ms = timestamp_raw

                # Validate timestamp is reasonable (2000-01-01 to 2100-01-01)
                if timestamp_ms < 946684800000 or timestamp_ms > 4102444800000:
                    logger.warning(f"Invalid timestamp {timestamp_raw} in row {row_num}, skipping")
                    continue

                dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

                result.append(
                    {
                        "timestamp": timestamp_ms,
                        "date": dt.isoformat(),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    }
                )
            except (ValueError, OSError) as e:
                logger.warning(f"Failed to parse row {row_num}: {e}, skipping")
                continue

        logger.info(f"Downloaded {len(result)} records for {symbol} {interval} {target_date}")

        # Persist to database
        if result:
            rows_inserted = upsert_crypto_ohlc(symbol=symbol, bar=interval, data=result)
            logger.info(
                f"Inserted {rows_inserted} records into database for {symbol} {interval} {target_date}"
            )

        return result

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"Data not available for {symbol} {interval} {target_date}")
        else:
            logger.error(f"HTTP error downloading {symbol} {interval} {target_date}: {e}")
        return []

    except Exception as e:
        logger.error(f"Failed to download {symbol} {interval} {target_date}: {e}")
        return []
