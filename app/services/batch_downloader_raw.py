"""Batch downloader without auto-commit for optimized bulk loading."""

from datetime import date, datetime, timezone
from typing import List, Dict, Any
import zipfile
import io
import csv
import httpx
import logging

logger = logging.getLogger(__name__)

BINANCE_VISION_BASE = "https://data.binance.vision/data/spot/daily/klines"


def get_download_url(symbol: str, interval: str, target_date: date) -> str:
    """Generate Binance Vision download URL."""
    date_str = target_date.strftime("%Y-%m-%d")
    filename = f"{symbol}-{interval}-{date_str}.zip"
    return f"{BINANCE_VISION_BASE}/{symbol}/{interval}/{filename}"


async def download_daily_data_raw(
    symbol: str,
    interval: str,
    target_date: date
) -> List[Dict[str, Any]]:
    """
    Download and parse daily K-line data WITHOUT database insertion.

    This version is for batch operations where database commits
    are managed externally for better performance.

    Returns:
        List of parsed K-line dictionaries or empty list on error
    """
    url = get_download_url(symbol, interval, target_date)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()

        # Extract CSV from ZIP
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            csv_filename = zip_file.namelist()[0]
            csv_content = zip_file.read(csv_filename).decode('utf-8')

        # Parse CSV
        result = []
        reader = csv.reader(io.StringIO(csv_content))
        for row in reader:
            if not row or len(row) < 6:
                continue

            timestamp_ms = int(row[0])
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            result.append({
                'timestamp': timestamp_ms,
                'date': dt.isoformat(),
                'open': float(row[1]),
                'high': float(row[2]),
                'low': float(row[3]),
                'close': float(row[4]),
                'volume': float(row[5])
            })

        return result

    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            logger.warning(f"HTTP {e.response.status_code} for {symbol} {interval} {target_date}")
        return []

    except Exception as e:
        logger.error(f"Failed to download {symbol} {interval} {target_date}: {e}")
        return []
