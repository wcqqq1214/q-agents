"""Crypto OHLC data operations for finance-agent.

This module provides functions for storing and retrieving cryptocurrency OHLC
(Open, High, Low, Close) data with support for multiple timeframes (bars).
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import sqlite3
from .schema import get_conn


def get_crypto_ohlc(
    symbol: str,
    bar: str,
    start: Optional[str] = None,
    end: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Query crypto OHLC data from database.

    Args:
        symbol: Cryptocurrency symbol (e.g., 'BTC-USDT')
        bar: Timeframe bar (e.g., '1m', '5m', '1h', '1d')
        start: Start date in ISO format (optional)
        end: End date in ISO format (optional)

    Returns:
        List of OHLC records as dictionaries
    """
    conn = get_conn()

    query = """
        SELECT symbol, timestamp, date, open, high, low, close, volume, bar
        FROM crypto_ohlc
        WHERE symbol = ? AND bar = ?
    """
    params = [symbol, bar]

    if start:
        query += " AND date >= ?"
        params.append(start)

    if end:
        query += " AND date <= ?"
        params.append(end)

    query += " ORDER BY timestamp ASC"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def upsert_crypto_ohlc(symbol: str, bar: str, data: List[Dict[str, Any]]) -> int:
    """Batch insert or update crypto OHLC data.

    Args:
        symbol: Cryptocurrency symbol
        bar: Timeframe bar
        data: List of OHLC records with keys: timestamp, date, open, high, low, close, volume

    Returns:
        Number of records inserted/updated
    """
    if not data:
        return 0

    conn = get_conn()

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

    records = [
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
        for record in data
    ]

    cursor = conn.executemany(query, records)
    count = cursor.rowcount
    conn.commit()
    conn.close()

    return count


def update_crypto_metadata(
    symbol: str,
    bar: str,
    start: str,
    end: str,
    total_records: int
) -> None:
    """Update crypto metadata for a symbol and timeframe.

    Args:
        symbol: Cryptocurrency symbol
        bar: Timeframe bar
        start: Data start date in ISO format
        end: Data end date in ISO format
        total_records: Total number of records
    """
    conn = get_conn()

    now = datetime.utcnow().isoformat()

    query = """
        INSERT INTO crypto_metadata (symbol, bar, last_update, data_start, data_end, total_records)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, bar) DO UPDATE SET
            last_update = excluded.last_update,
            data_start = excluded.data_start,
            data_end = excluded.data_end,
            total_records = excluded.total_records
    """

    conn.execute(query, (symbol, bar, now, start, end, total_records))
    conn.commit()
    conn.close()


def get_crypto_metadata(symbol: str, bar: str) -> Optional[Dict[str, Any]]:
    """Get crypto metadata for a symbol and timeframe.

    Args:
        symbol: Cryptocurrency symbol
        bar: Timeframe bar

    Returns:
        Metadata dictionary or None if not found
    """
    conn = get_conn()

    query = """
        SELECT symbol, bar, last_update, data_start, data_end, total_records
        FROM crypto_metadata
        WHERE symbol = ? AND bar = ?
    """

    cursor = conn.execute(query, (symbol, bar))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None
