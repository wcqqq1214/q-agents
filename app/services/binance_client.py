"""Binance REST API client for fetching K-line data."""
from typing import List, Dict, Any
from datetime import datetime, timezone
import httpx
import logging

logger = logging.getLogger(__name__)

BINANCE_API_BASE = "https://api.binance.com"


def parse_kline_response(raw_klines: List[List[Any]]) -> List[Dict[str, Any]]:
    """
    Parse Binance K-line API response into standardized format.

    Args:
        raw_klines: Raw K-line data from Binance API

    Returns:
        List of dictionaries with keys: timestamp, date, open, high, low, close, volume
    """
    if not raw_klines:
        return []

    result = []
    for kline in raw_klines:
        timestamp_ms = kline[0]
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

        result.append({
            'timestamp': timestamp_ms,
            'date': dt.isoformat(),
            'open': float(kline[1]),
            'high': float(kline[2]),
            'low': float(kline[3]),
            'close': float(kline[4]),
            'volume': float(kline[5])
        })

    return result


async def fetch_binance_klines(
    symbol: str,
    interval: str,
    start_time: int,
    end_time: int,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Fetch K-line data from Binance REST API.

    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        interval: K-line interval (e.g., "1m", "1h", "1d")
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
        limit: Maximum number of records to fetch (default 1000, max 1000)

    Returns:
        List of parsed K-line dictionaries

    Raises:
        httpx.HTTPError: If API request fails
    """
    url = f"{BINANCE_API_BASE}/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time,
        "endTime": end_time,
        "limit": min(limit, 1000)  # Binance max is 1000
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        raw_klines = response.json()

    return parse_kline_response(raw_klines)


async def fetch_klines_with_pagination(
    symbol: str,
    interval: str,
    start_time: int,
    end_time: int
) -> List[Dict[str, Any]]:
    """
    Fetch K-line data from Binance with automatic pagination.

    Handles Binance's 1000-record limit by making multiple requests
    and combining results into a single list.

    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        interval: K-line interval (e.g., "1m", "1h", "1d")
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds

    Returns:
        Complete list of K-line data for the entire time range

    Raises:
        httpx.HTTPError: If any API request fails
    """
    all_klines = []
    current_start = start_time

    while current_start < end_time:
        batch = await fetch_binance_klines(
            symbol=symbol,
            interval=interval,
            start_time=current_start,
            end_time=end_time,
            limit=1000
        )

        if not batch:
            break

        all_klines.extend(batch)

        if len(batch) < 1000:
            break

        last_timestamp = batch[-1]['timestamp']

        if last_timestamp >= end_time:
            break

        current_start = last_timestamp + 1

    logger.info(f"Fetched {len(all_klines)} records for {symbol} {interval} with pagination")
    return all_klines
