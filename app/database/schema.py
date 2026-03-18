"""SQLite database schema and connection management for finance-agent.

This module provides the database schema for storing historical OHLC data, news
articles, and multi-layer pipeline results for the Magnificent Seven stocks.
"""

import sqlite3
from pathlib import Path
from typing import Optional

# Database schema with alignment and pipeline tables
SCHEMA = """
CREATE TABLE IF NOT EXISTS tickers (
    symbol        TEXT PRIMARY KEY,
    name          TEXT,
    last_ohlc_fetch   TEXT,
    last_news_fetch   TEXT
);

CREATE TABLE IF NOT EXISTS ohlc (
    symbol        TEXT NOT NULL,
    date          TEXT NOT NULL,
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL,
    volume        REAL,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_ohlc_symbol_date ON ohlc(symbol, date DESC);

CREATE TABLE IF NOT EXISTS news (
    id            TEXT PRIMARY KEY,
    symbol        TEXT NOT NULL,
    published_utc TEXT NOT NULL,
    title         TEXT,
    description   TEXT,
    article_url   TEXT,
    publisher     TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_symbol_date ON news(symbol, published_utc DESC);

-- News-to-trading-day alignment with forward returns
CREATE TABLE IF NOT EXISTS news_aligned (
    news_id       TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    trade_date    TEXT NOT NULL,
    published_utc TEXT,
    ret_t0        REAL,
    ret_t1        REAL,
    ret_t3        REAL,
    ret_t5        REAL,
    ret_t10       REAL,
    PRIMARY KEY (news_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_news_aligned_symbol_date ON news_aligned(symbol, trade_date);

-- Layer 0: Rule-based filter results
CREATE TABLE IF NOT EXISTS layer0_results (
    news_id       TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    passed        INTEGER NOT NULL,
    reason        TEXT,
    PRIMARY KEY (news_id, symbol)
);

-- Layer 1: LLM semantic extraction results
CREATE TABLE IF NOT EXISTS layer1_results (
    news_id       TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    relevance     TEXT,
    key_discussion      TEXT,
    sentiment           TEXT,
    reason_growth       TEXT,
    reason_decrease     TEXT,
    PRIMARY KEY (news_id, symbol)
);

-- Batch API job tracking
CREATE TABLE IF NOT EXISTS batch_jobs (
    batch_id      TEXT PRIMARY KEY,
    symbol        TEXT,
    status        TEXT,
    total         INTEGER,
    completed     INTEGER DEFAULT 0,
    created_at    TEXT,
    finished_at   TEXT
);
"""

# Default database path
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "finance_data.db"


def get_conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a database connection with optimized settings.

    Args:
        db_path: Path to the SQLite database file. If None, uses default path.

    Returns:
        A configured SQLite connection with Row factory enabled.
    """
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize the database schema.

    Args:
        db_path: Path to the SQLite database file. If None, uses default path.
    """
    conn = get_conn(db_path)
    conn.executescript(SCHEMA)

    # Insert Magnificent Seven tickers if not exists
    mag_seven = [
        ("AAPL", "Apple Inc."),
        ("MSFT", "Microsoft Corporation"),
        ("GOOGL", "Alphabet Inc."),
        ("AMZN", "Amazon.com Inc."),
        ("META", "Meta Platforms Inc."),
        ("NVDA", "NVIDIA Corporation"),
        ("TSLA", "Tesla Inc."),
    ]

    for symbol, name in mag_seven:
        conn.execute(
            "INSERT OR IGNORE INTO tickers (symbol, name) VALUES (?, ?)",
            (symbol, name),
        )

    conn.commit()
    conn.close()

    path = db_path or DEFAULT_DB_PATH
    print(f"Database initialized at {path}")


if __name__ == "__main__":
    init_db()
