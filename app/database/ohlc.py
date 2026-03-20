"""OHLC data operations for the database."""

import sqlite3
import logging
from typing import List, Dict, Optional
from datetime import datetime

from app.database.schema import get_conn

logger = logging.getLogger(__name__)


def get_ohlc(symbol: str, start: str, end: str) -> List[Dict]:
    """Query OHLC data from database.

    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        start: Start date in YYYY-MM-DD format
        end: End date in YYYY-MM-DD format

    Returns:
        List of OHLC records as dictionaries
    """
    conn = get_conn()
    query = """
        SELECT date, open, high, low, close, volume
        FROM ohlc
        WHERE symbol = ? AND date >= ? AND date <= ?
        ORDER BY date ASC
    """
    rows = conn.execute(query, (symbol.upper(), start, end)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_ohlc_aggregated(symbol: str, start: str, end: str, interval: str) -> List[Dict]:
    """Query aggregated OHLC data from database.

    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        start: Start date in YYYY-MM-DD format
        end: End date in YYYY-MM-DD format
        interval: Time granularity ('day', 'week', 'month', 'year')

    Returns:
        List of aggregated OHLC records as dictionaries
    """
    conn = get_conn()

    if interval == 'day':
        # Direct query, no aggregation needed
        query = """
            SELECT date, open, high, low, close, volume
            FROM ohlc
            WHERE symbol = ? AND date >= ? AND date <= ?
            ORDER BY date ASC
        """
        params = (symbol.upper(), start, end)
    elif interval == 'week':
        # Aggregate by ISO week (Monday to Sunday)
        query = """
            SELECT
                date(date, 'weekday 0', '-6 days') as date,
                (SELECT open FROM ohlc o2
                 WHERE o2.symbol = ohlc.symbol
                 AND date(o2.date, 'weekday 0', '-6 days') = date(ohlc.date, 'weekday 0', '-6 days')
                 ORDER BY o2.date ASC LIMIT 1) as open,
                MAX(high) as high,
                MIN(low) as low,
                (SELECT close FROM ohlc o3
                 WHERE o3.symbol = ohlc.symbol
                 AND date(o3.date, 'weekday 0', '-6 days') = date(ohlc.date, 'weekday 0', '-6 days')
                 ORDER BY o3.date DESC LIMIT 1) as close,
                SUM(volume) as volume
            FROM ohlc
            WHERE symbol = ? AND date >= ? AND date <= ?
            GROUP BY date(date, 'weekday 0', '-6 days')
            ORDER BY date ASC
        """
        params = (symbol.upper(), start, end)
    elif interval == 'month':
        # Aggregate by calendar month
        query = """
            SELECT
                strftime('%Y-%m-01', date) as date,
                (SELECT open FROM ohlc o2
                 WHERE o2.symbol = ohlc.symbol
                 AND strftime('%Y-%m', o2.date) = strftime('%Y-%m', ohlc.date)
                 ORDER BY o2.date ASC LIMIT 1) as open,
                MAX(high) as high,
                MIN(low) as low,
                (SELECT close FROM ohlc o3
                 WHERE o3.symbol = ohlc.symbol
                 AND strftime('%Y-%m', o3.date) = strftime('%Y-%m', ohlc.date)
                 ORDER BY o3.date DESC LIMIT 1) as close,
                SUM(volume) as volume
            FROM ohlc
            WHERE symbol = ? AND date >= ? AND date <= ?
            GROUP BY strftime('%Y-%m', date)
            ORDER BY date ASC
        """
        params = (symbol.upper(), start, end)
    elif interval == 'year':
        # Aggregate by calendar year
        query = """
            SELECT
                strftime('%Y-01-01', date) as date,
                (SELECT open FROM ohlc o2
                 WHERE o2.symbol = ohlc.symbol
                 AND strftime('%Y', o2.date) = strftime('%Y', ohlc.date)
                 ORDER BY o2.date ASC LIMIT 1) as open,
                MAX(high) as high,
                MIN(low) as low,
                (SELECT close FROM ohlc o3
                 WHERE o3.symbol = ohlc.symbol
                 AND strftime('%Y', o3.date) = strftime('%Y', ohlc.date)
                 ORDER BY o3.date DESC LIMIT 1) as close,
                SUM(volume) as volume
            FROM ohlc
            WHERE symbol = ? AND date >= ? AND date <= ?
            GROUP BY strftime('%Y', date)
            ORDER BY date ASC
        """
        params = (symbol.upper(), start, end)
    else:
        conn.close()
        raise ValueError(f"Invalid interval: {interval}")

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def upsert_ohlc(symbol: str, data: List[Dict]):
    """Insert or update OHLC data (batch operation).

    Args:
        symbol: Stock symbol
        data: List of dicts with keys: date, open, high, low, close, volume
    """
    if not data:
        return

    conn = get_conn()
    conn.executemany("""
        INSERT INTO ohlc (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, date) DO NOTHING
    """, [(symbol.upper(), d['date'], d['open'], d['high'], d['low'], d['close'], d['volume'])
          for d in data])
    conn.commit()
    conn.close()
    logger.info(f"Upserted {len(data)} records for {symbol}")


def update_metadata(symbol: str, start: str, end: str):
    """Update metadata after data sync.

    Args:
        symbol: Stock symbol
        start: Data start date
        end: Data end date
    """
    conn = get_conn()

    # Check if data_metadata table exists, if not create it
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_metadata (
            symbol TEXT PRIMARY KEY,
            last_update TEXT,
            data_start TEXT,
            data_end TEXT
        )
    """)

    conn.execute("""
        INSERT INTO data_metadata (symbol, last_update, data_start, data_end)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            last_update = excluded.last_update,
            data_end = excluded.data_end
    """, (symbol.upper(), datetime.now().isoformat(), start, end))
    conn.commit()
    conn.close()


def get_metadata(symbol: str) -> Optional[Dict]:
    """Get metadata for a symbol."""
    conn = get_conn()

    # Check if data_metadata table exists
    table_exists = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='data_metadata'
    """).fetchone()

    if not table_exists:
        conn.close()
        return None

    row = conn.execute(
        "SELECT * FROM data_metadata WHERE symbol = ?",
        (symbol.upper(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None
