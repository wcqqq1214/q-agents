"""Check recent BTC data to understand the gap."""

import sqlite3
from pathlib import Path

db_path = Path("data/finance_data.db")
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

# Check recent BTC daily data
query = """
    SELECT date, timestamp
    FROM crypto_ohlc
    WHERE symbol = 'BTC-USDT' AND bar = '1d'
    AND date >= '2024-12-01'
    ORDER BY date DESC
    LIMIT 30
"""

cursor = conn.execute(query)
rows = cursor.fetchall()

print("Recent BTC-USDT 1d data:")
print(f"{'Date':<30} {'Timestamp':<15}")
print("-" * 50)
for row in rows:
    print(f"{row['date']:<30} {row['timestamp']:<15}")

print(f"\nTotal records: {len(rows)}")

# Check for the gap
query2 = """
    SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as count
    FROM crypto_ohlc
    WHERE symbol = 'BTC-USDT' AND bar = '1d'
    AND date >= '2025-01-01'
"""

cursor = conn.execute(query2)
row = cursor.fetchone()
print(f"\n2025 data summary:")
print(f"  Min date: {row['min_date']}")
print(f"  Max date: {row['max_date']}")
print(f"  Count: {row['count']}")

conn.close()
