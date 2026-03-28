"""Merge duplicate symbol data in database.

The database has data stored under both 'BTCUSDT' and 'BTC-USDT' formats.
This script merges them into the correct format (BTC-USDT).
"""

import sqlite3
from pathlib import Path

db_path = Path("data/finance_data.db")
conn = sqlite3.connect(str(db_path))

print("=" * 80)
print("Merging duplicate symbol data")
print("=" * 80)

# Check current state
cursor = conn.execute("""
    SELECT symbol, bar, COUNT(*) as count
    FROM crypto_ohlc
    GROUP BY symbol, bar
    ORDER BY symbol, bar
""")

print("\nCurrent state:")
for row in cursor.fetchall():
    print(f"  {row[0]:<15} {row[1]:<10} {row[2]:>10} records")

# Merge BTCUSDT -> BTC-USDT
print("\nMerging BTCUSDT -> BTC-USDT...")
cursor = conn.execute("""
    UPDATE crypto_ohlc
    SET symbol = 'BTC-USDT'
    WHERE symbol = 'BTCUSDT'
""")
print(f"  Updated {cursor.rowcount} records")

# Merge ETHUSDT -> ETH-USDT
print("\nMerging ETHUSDT -> ETH-USDT...")
cursor = conn.execute("""
    UPDATE crypto_ohlc
    SET symbol = 'ETH-USDT'
    WHERE symbol = 'ETHUSDT'
""")
print(f"  Updated {cursor.rowcount} records")

conn.commit()

# Check final state
cursor = conn.execute("""
    SELECT symbol, bar, COUNT(*) as count, MIN(date) as min_date, MAX(date) as max_date
    FROM crypto_ohlc
    GROUP BY symbol, bar
    ORDER BY symbol, bar
""")

print("\nFinal state:")
print(f"{'Symbol':<15} {'Bar':<10} {'Records':>10} {'From':<25} {'To':<25}")
print("-" * 90)
for row in cursor.fetchall():
    print(f"{row[0]:<15} {row[1]:<10} {row[2]:>10} {row[3]:<25} {row[4]:<25}")

conn.close()

print("\n✓ Merge completed!")
