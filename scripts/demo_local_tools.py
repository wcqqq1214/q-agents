"""Test script for local database tools."""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.local_tools import (
    get_local_stock_data,
    search_local_historical_news,
)


def test_local_stock_data():
    """Test get_local_stock_data tool."""
    print("=" * 60)
    print("Testing get_local_stock_data")
    print("=" * 60)

    result = get_local_stock_data.invoke({"ticker": "NVDA", "days": 60})
    data = json.loads(result)

    if "error" in data:
        print(f"❌ Error: {data['error']}")
    else:
        print(f"✓ Ticker: {data['ticker']}")
        print(f"✓ Period: {data['period_days']} days")
        print(f"✓ Last date: {data['last_date']}")
        print(f"✓ Last close: ${data['last_close']:.2f}")
        print(f"✓ SMA(20): ${data['sma_20']:.2f}")
        print(f"✓ MACD: {data['macd_line']:.4f}")
        print(f"✓ Price change: {data['price_change_pct']:.2f}%")

    print()


def test_local_historical_news():
    """Test search_local_historical_news tool."""
    print("=" * 60)
    print("Testing search_local_historical_news")
    print("=" * 60)

    result = search_local_historical_news.invoke({
        "ticker": "TSLA",
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "limit": 5,
    })
    data = json.loads(result)

    if "error" in data:
        print(f"❌ Error: {data['error']}")
    else:
        print(f"✓ Ticker: {data['ticker']}")
        print(f"✓ Date range: {data['start_date']} to {data['end_date']}")
        print(f"✓ Found {data['count']} articles")
        print()

        for i, article in enumerate(data["articles"][:3], 1):
            print(f"  [{i}] {article['published_utc']}")
            print(f"      {article['title']}")
            print(f"      Source: {article['publisher']}")
            print()

    print()


if __name__ == "__main__":
    print("\n🧪 Testing Local Database Tools\n")

    test_local_stock_data()
    test_local_historical_news()

    print("=" * 60)
    print("Tests complete!")
    print("=" * 60)
