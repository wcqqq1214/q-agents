"""Batch operations for crypto OHLC data with optimized performance."""

from typing import List, Dict, Any
from datetime import datetime
import sqlite3
import logging

from app.database.schema import get_conn

logger = logging.getLogger(__name__)


class BatchInserter:
    """Batch inserter for crypto OHLC data with transaction management."""

    def __init__(self, batch_size: int = 5000):
        """
        Initialize batch inserter.

        Args:
            batch_size: Number of records to accumulate before committing
        """
        self.batch_size = batch_size
        self.buffer: List[tuple] = []
        self.conn = None
        self.total_inserted = 0

    def __enter__(self):
        """Enter context manager."""
        self.conn = get_conn()
        # Enable WAL mode and optimizations
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-64000")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and flush remaining records."""
        if exc_type is None:
            self.flush()
        if self.conn:
            self.conn.close()

    def add_records(self, symbol: str, bar: str, data: List[Dict[str, Any]]):
        """
        Add records to buffer.

        Args:
            symbol: Cryptocurrency symbol
            bar: Timeframe bar
            data: List of OHLC records
        """
        for record in data:
            self.buffer.append((
                symbol,
                record['timestamp'],
                record['date'],
                record['open'],
                record['high'],
                record['low'],
                record['close'],
                record['volume'],
                bar
            ))

        # Auto-flush if buffer is full
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        """Flush buffer to database."""
        if not self.buffer or not self.conn:
            return

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

        try:
            cursor = self.conn.executemany(query, self.buffer)
            self.conn.commit()
            self.total_inserted += len(self.buffer)
            logger.info(f"Flushed {len(self.buffer)} records to database (total: {self.total_inserted})")
            self.buffer.clear()
        except Exception as e:
            logger.error(f"Failed to flush batch: {e}")
            self.conn.rollback()
            raise
