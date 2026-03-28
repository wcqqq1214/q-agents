"""SQLite database operations for OHLC data."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "finance.db"


def get_conn() -> sqlite3.Connection:
    """Get database connection with WAL mode for concurrent reads."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database tables and indexes."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ohlc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date)
        );

        CREATE INDEX IF NOT EXISTS idx_ohlc_symbol_date
        ON ohlc(symbol, date);

        CREATE TABLE IF NOT EXISTS data_metadata (
            symbol TEXT PRIMARY KEY,
            last_update TEXT,
            data_start TEXT,
            data_end TEXT
        );
    """)
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


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


def upsert_ohlc(symbol: str, data: List[Dict]):
    """Insert or update OHLC data (batch operation).

    Args:
        symbol: Stock symbol
        data: List of dicts with keys: date, open, high, low, close, volume
    """
    if not data:
        return

    conn = get_conn()
    conn.executemany(
        """
        INSERT INTO ohlc (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, date) DO NOTHING
    """,
        [
            (
                symbol.upper(),
                d["date"],
                d["open"],
                d["high"],
                d["low"],
                d["close"],
                d["volume"],
            )
            for d in data
        ],
    )
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
    conn.execute(
        """
        INSERT INTO data_metadata (symbol, last_update, data_start, data_end)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            last_update = excluded.last_update,
            data_end = excluded.data_end
    """,
        (symbol.upper(), datetime.now().isoformat(), start, end),
    )
    conn.commit()
    conn.close()


def get_metadata(symbol: str) -> Optional[Dict]:
    """Get metadata for a symbol."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM data_metadata WHERE symbol = ?", (symbol.upper(),)).fetchone()
    conn.close()
    return dict(row) if row else None
