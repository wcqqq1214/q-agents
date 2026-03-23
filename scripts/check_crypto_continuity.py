"""Check crypto data continuity in database.

This script analyzes the crypto_ohlc table to identify gaps in the data.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Tuple
import os


def get_db_path() -> str:
    """Get database path from environment or use default."""
    return os.getenv("DB_PATH", "data/finance_data.db")


def check_continuity(symbol: str, bar: str) -> None:
    """Check data continuity for a given symbol and bar.

    Args:
        symbol: Cryptocurrency symbol (e.g., 'BTC-USDT')
        bar: Timeframe bar (e.g., '1m', '1d')
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get all timestamps for this symbol/bar
    query = """
        SELECT timestamp, date
        FROM crypto_ohlc
        WHERE symbol = ? AND bar = ?
        ORDER BY timestamp ASC
    """

    cursor = conn.execute(query, (symbol, bar))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print(f"❌ No data found for {symbol} {bar}")
        return

    print(f"\n{'='*80}")
    print(f"Checking continuity for {symbol} {bar}")
    print(f"{'='*80}")
    print(f"Total records: {len(rows)}")
    print(f"First record: {rows[0]['date']} (timestamp: {rows[0]['timestamp']})")
    print(f"Last record: {rows[-1]['date']} (timestamp: {rows[-1]['timestamp']})")

    # Calculate expected interval in milliseconds
    interval_ms = {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
    }

    expected_interval = interval_ms.get(bar)
    if not expected_interval:
        print(f"⚠️  Unknown bar interval: {bar}")
        return

    # Check for gaps
    gaps = []
    for i in range(1, len(rows)):
        prev_ts = rows[i-1]['timestamp']
        curr_ts = rows[i]['timestamp']
        diff = curr_ts - prev_ts

        if diff > expected_interval:
            # Calculate how many intervals are missing
            missing_intervals = (diff // expected_interval) - 1
            gaps.append({
                'from': rows[i-1]['date'],
                'to': rows[i]['date'],
                'from_ts': prev_ts,
                'to_ts': curr_ts,
                'gap_ms': diff,
                'missing_intervals': missing_intervals
            })

    if gaps:
        print(f"\n❌ Found {len(gaps)} gaps in data:")
        print(f"\n{'From':<20} {'To':<20} {'Gap (ms)':<15} {'Missing Intervals'}")
        print(f"{'-'*80}")
        for gap in gaps:
            print(f"{gap['from']:<20} {gap['to']:<20} {gap['gap_ms']:<15} {int(gap['missing_intervals'])}")

        # Show detailed info for first few gaps
        print(f"\n📊 Detailed gap analysis (first 5):")
        for i, gap in enumerate(gaps[:5]):
            print(f"\nGap {i+1}:")
            print(f"  From: {gap['from']} (ts: {gap['from_ts']})")
            print(f"  To: {gap['to']} (ts: {gap['to_ts']})")
            print(f"  Duration: {gap['gap_ms']} ms ({gap['gap_ms'] / 1000 / 60:.2f} minutes)")
            print(f"  Missing intervals: {int(gap['missing_intervals'])}")
    else:
        print(f"\n✅ No gaps found! Data is continuous.")


def get_summary() -> None:
    """Get summary of all crypto data in database."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT symbol, bar, COUNT(*) as count, MIN(date) as min_date, MAX(date) as max_date
        FROM crypto_ohlc
        GROUP BY symbol, bar
        ORDER BY symbol, bar
    """

    cursor = conn.execute(query)
    rows = cursor.fetchall()
    conn.close()

    print(f"\n{'='*80}")
    print(f"Database Summary")
    print(f"{'='*80}")
    print(f"Database path: {db_path}")
    print(f"\n{'Symbol':<15} {'Bar':<10} {'Records':<12} {'From':<20} {'To':<20}")
    print(f"{'-'*80}")

    for row in rows:
        print(f"{row['symbol']:<15} {row['bar']:<10} {row['count']:<12} {row['min_date']:<20} {row['max_date']:<20}")


if __name__ == "__main__":
    # Get summary first
    get_summary()

    # Check continuity for each symbol/bar combination
    symbols = ["BTC-USDT", "ETH-USDT"]
    bars = ["1m", "1d"]

    for symbol in symbols:
        for bar in bars:
            check_continuity(symbol, bar)
