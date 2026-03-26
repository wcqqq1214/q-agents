"""Redis-first hot cache with in-memory fallback."""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import redis

from app.services.redis_client import (
    get_sync_redis_client,
    is_redis_enabled,
    redis_circuit_breaker,
)

logger = logging.getLogger(__name__)

# Global hot cache structure: {symbol: {interval: DataFrame}}
# Supports BTCUSDT and ETHUSDT with various intervals
HOT_CACHE: Dict[str, Dict[str, pd.DataFrame]] = {
    "BTCUSDT": {},
    "ETHUSDT": {},
}

# Expected DataFrame columns
CACHE_COLUMNS = ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']
CACHE_TTLS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def _empty_cache_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=CACHE_COLUMNS)


def _cache_key(symbol: str, interval: str) -> str:
    return f"cache:kline:{symbol}:{interval}:latest"


def _cache_ttl(interval: str) -> int:
    return CACHE_TTLS.get(interval, 300)


def _normalize_dataframe(data: Any) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        frame = data.copy()
    elif isinstance(data, list):
        frame = pd.DataFrame(data) if data else _empty_cache_frame()
    else:
        frame = _empty_cache_frame()

    for column in CACHE_COLUMNS:
        if column not in frame.columns:
            frame[column] = None

    frame = frame[CACHE_COLUMNS]
    return frame


def _merge_frames(current: pd.DataFrame, new_data: Any) -> pd.DataFrame:
    new_df = _normalize_dataframe(new_data)
    combined = pd.concat([current, new_df], ignore_index=True)

    if 'timestamp' in combined.columns and len(combined) > 0:
        combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
        combined = combined.sort_values('timestamp').reset_index(drop=True)

    if len(combined) > 2880:
        combined = combined.tail(2880).reset_index(drop=True)

    return combined[CACHE_COLUMNS] if not combined.empty else _empty_cache_frame()


def _serialize_dataframe(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    normalized = _normalize_dataframe(df)
    normalized.to_parquet(buffer, engine='pyarrow', compression='snappy', index=False)
    return buffer.getvalue()


def _deserialize_dataframe(payload: bytes) -> pd.DataFrame:
    if not payload:
        return _empty_cache_frame()

    frame = pd.read_parquet(io.BytesIO(payload))
    return _normalize_dataframe(frame)


def clear_memory_cache() -> None:
    """Clear the in-memory fallback cache."""
    for symbol in HOT_CACHE:
        HOT_CACHE[symbol] = {}


def _read_memory_cache(symbol: str, interval: str) -> pd.DataFrame:
    if symbol not in HOT_CACHE:
        logger.debug("Symbol %s not in memory cache", symbol)
        return _empty_cache_frame()

    if interval not in HOT_CACHE[symbol]:
        logger.debug("Interval %s not in memory cache for %s", interval, symbol)
        return _empty_cache_frame()

    return HOT_CACHE[symbol][interval].copy()


def _write_memory_cache(symbol: str, interval: str, data: Any) -> None:
    if symbol not in HOT_CACHE:
        HOT_CACHE[symbol] = {}
    current = HOT_CACHE[symbol].get(interval, _empty_cache_frame())
    HOT_CACHE[symbol][interval] = _merge_frames(current, data)


def _cleanup_memory_cache(symbol: str, interval: str, cutoff_date: datetime) -> None:
    if symbol not in HOT_CACHE or interval not in HOT_CACHE[symbol]:
        return

    df = HOT_CACHE[symbol][interval]
    if len(df) == 0:
        return

    cutoff_timestamp = int(cutoff_date.timestamp() * 1000)
    HOT_CACHE[symbol][interval] = df[df['timestamp'] >= cutoff_timestamp].reset_index(drop=True)


def _should_attempt_redis() -> bool:
    return is_redis_enabled() and redis_circuit_breaker.can_attempt()


def get_hot_cache(symbol: str, interval: str) -> pd.DataFrame:
    """
    Get hot cache data for a symbol and interval.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Time interval (e.g., '1m', '5m')

    Returns:
        DataFrame copy with cache data, or empty DataFrame with correct columns
    """
    if _should_attempt_redis():
        try:
            client = get_sync_redis_client()
            if client is not None:
                payload = client.get(_cache_key(symbol, interval))
                recovered = redis_circuit_breaker.record_success()
                if recovered:
                    clear_memory_cache()
                if payload is None:
                    return _empty_cache_frame()
                return _deserialize_dataframe(payload)
        except (redis.RedisError, OSError, ValueError) as exc:
            redis_circuit_breaker.record_failure()
            logger.warning("Redis hot-cache read failed, falling back to memory: %s", exc)

    return _read_memory_cache(symbol, interval)


def append_to_hot_cache(
    symbol: str,
    interval: str,
    new_data: List[Dict[str, Any]]
) -> None:
    """
    Append new data to hot cache with deduplication.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Time interval (e.g., '1m', '5m')
        new_data: List of K-line dictionaries
    """
    if _should_attempt_redis():
        try:
            client = get_sync_redis_client()
            if client is not None:
                payload = client.get(_cache_key(symbol, interval))
                current = _deserialize_dataframe(payload) if payload else _empty_cache_frame()
                combined = _merge_frames(current, new_data)
                client.set(
                    _cache_key(symbol, interval),
                    _serialize_dataframe(combined),
                    ex=_cache_ttl(interval),
                )
                recovered = redis_circuit_breaker.record_success()
                if recovered:
                    clear_memory_cache()
                logger.info("Appended data to Redis hot cache for %s %s, now %s records", symbol, interval, len(combined))
                return
        except (redis.RedisError, OSError, ValueError) as exc:
            redis_circuit_breaker.record_failure()
            logger.warning("Redis hot-cache write failed, falling back to memory: %s", exc)

    _write_memory_cache(symbol, interval, new_data)
    logger.info("Appended data to memory hot cache for %s %s", symbol, interval)


def cleanup_hot_cache(symbol: str, interval: str, cutoff_date: datetime) -> None:
    """
    Remove data before cutoff date from hot cache.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Time interval (e.g., '1m', '5m')
        cutoff_date: Remove data before this datetime
    """
    if _should_attempt_redis():
        try:
            client = get_sync_redis_client()
            if client is not None:
                payload = client.get(_cache_key(symbol, interval))
                if not payload:
                    redis_circuit_breaker.record_success()
                    return

                df = _deserialize_dataframe(payload)
                cutoff_timestamp = int(cutoff_date.timestamp() * 1000)
                df_filtered = df[df['timestamp'] >= cutoff_timestamp].reset_index(drop=True)
                if df_filtered.empty:
                    client.delete(_cache_key(symbol, interval))
                else:
                    client.set(
                        _cache_key(symbol, interval),
                        _serialize_dataframe(df_filtered),
                        ex=_cache_ttl(interval),
                    )
                recovered = redis_circuit_breaker.record_success()
                if recovered:
                    clear_memory_cache()
                return
        except (redis.RedisError, OSError, ValueError) as exc:
            redis_circuit_breaker.record_failure()
            logger.warning("Redis hot-cache cleanup failed, falling back to memory: %s", exc)

    _cleanup_memory_cache(symbol, interval, cutoff_date)


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
                size = df.memory_usage(deep=True).sum()
                total_size += size
                logger.debug("%s %s memory cache size: %s bytes", symbol, interval, size)

    return total_size
