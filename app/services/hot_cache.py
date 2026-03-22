"""
Hot cache infrastructure for crypto K-line data.

This module provides in-memory caching for real-time crypto K-line data
using pandas DataFrames. The cache stores up to 48 hours (2880 records)
of 1-minute data for BTCUSDT and ETHUSDT.
"""
import logging
import sys
from typing import Dict
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

# Global hot cache structure: {symbol: {interval: DataFrame}}
# Supports BTCUSDT and ETHUSDT with various intervals
HOT_CACHE: Dict[str, Dict[str, pd.DataFrame]] = {
    "BTCUSDT": {},
    "ETHUSDT": {},
}

# Expected DataFrame columns
CACHE_COLUMNS = ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']


def get_hot_cache(symbol: str, interval: str) -> pd.DataFrame:
    """
    Get hot cache data for a symbol and interval.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Time interval (e.g., '1m', '5m')

    Returns:
        DataFrame copy with cache data, or empty DataFrame with correct columns
    """
    if symbol not in HOT_CACHE:
        logger.debug(f"Symbol {symbol} not in hot cache, returning empty DataFrame")
        return pd.DataFrame(columns=CACHE_COLUMNS)

    if interval not in HOT_CACHE[symbol]:
        logger.debug(f"Interval {interval} not in hot cache for {symbol}, returning empty DataFrame")
        return pd.DataFrame(columns=CACHE_COLUMNS)

    # Return a copy to prevent external modifications
    return HOT_CACHE[symbol][interval].copy()


def append_to_hot_cache(
    symbol: str,
    interval: str,
    new_data: pd.DataFrame,
    max_records: int = 2880
) -> None:
    """
    Append new data to hot cache with deduplication.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Time interval (e.g., '1m', '5m')
        new_data: DataFrame with new K-line data
        max_records: Maximum number of records to keep (default: 2880 for 48 hours)
    """
    if symbol not in HOT_CACHE:
        logger.warning(f"Symbol {symbol} not in hot cache structure")
        return

    # Initialize interval cache if it doesn't exist
    if interval not in HOT_CACHE[symbol]:
        HOT_CACHE[symbol][interval] = pd.DataFrame(columns=CACHE_COLUMNS)
        logger.debug(f"Initialized hot cache for {symbol} {interval}")

    # Append new data
    combined = pd.concat([HOT_CACHE[symbol][interval], new_data], ignore_index=True)

    # Deduplicate by timestamp, keeping last (newer data wins)
    if 'timestamp' in combined.columns and len(combined) > 0:
        combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
        combined = combined.sort_values('timestamp').reset_index(drop=True)

    # Limit to max_records (keep most recent)
    if len(combined) > max_records:
        combined = combined.tail(max_records).reset_index(drop=True)
        logger.debug(f"Trimmed {symbol} {interval} cache to {max_records} records")

    HOT_CACHE[symbol][interval] = combined
    logger.info(f"Appended data to {symbol} {interval} cache, now {len(combined)} records")


def cleanup_hot_cache(symbol: str, interval: str, cutoff_date: datetime) -> None:
    """
    Remove data before cutoff date from hot cache.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Time interval (e.g., '1m', '5m')
        cutoff_date: Remove data before this datetime
    """
    if symbol not in HOT_CACHE:
        logger.debug(f"Symbol {symbol} not in hot cache")
        return

    if interval not in HOT_CACHE[symbol]:
        logger.debug(f"Interval {interval} not in hot cache for {symbol}")
        return

    df = HOT_CACHE[symbol][interval]
    if len(df) == 0:
        return

    # Filter data after cutoff
    original_len = len(df)
    df_filtered = df[df['date'] >= cutoff_date].reset_index(drop=True)

    HOT_CACHE[symbol][interval] = df_filtered
    removed = original_len - len(df_filtered)

    if removed > 0:
        logger.info(f"Cleaned up {removed} records from {symbol} {interval} cache before {cutoff_date}")


def get_cache_size() -> int:
    """
    Get total cache size in bytes.

    Returns:
        Total memory usage of all cached DataFrames in bytes
    """
    total_size = 0

    for symbol, intervals in HOT_CACHE.items():
        for interval, df in intervals.items():
            if len(df) > 0:
                # Get memory usage including index
                size = df.memory_usage(deep=True).sum()
                total_size += size
                logger.debug(f"{symbol} {interval} cache size: {size} bytes")

    return total_size
