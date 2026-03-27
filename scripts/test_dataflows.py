# scripts/test_dataflows.py
"""Smoke test for data provider abstraction layer"""
import asyncio
from datetime import datetime, timedelta
from app.dataflows.interface import DataFlowRouter

async def main():
    print("🧪 Testing Data Provider Abstraction Layer\n")

    router = DataFlowRouter(enable_cache=False)

    # Test 1: Stock data
    print("1️⃣  Testing stock data...")
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        candles = await router.get_stock_data("AAPL", start_date, end_date)
        print(f"   ✓ Retrieved {len(candles)} candles for AAPL")
        print(f"   ✓ Latest close: ${candles[-1].close:.2f}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Test 2: News
    print("\n2️⃣  Testing news search...")
    try:
        articles = await router.get_news("AAPL", limit=5)
        print(f"   ✓ Retrieved {len(articles)} news articles")
        if articles:
            print(f"   ✓ Latest: {articles[0].title[:60]}...")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Test 3: Cache hit
    print("\n3️⃣  Testing cache...")
    try:
        candles2 = await router.get_stock_data("AAPL", start_date, end_date)
        print(f"   ✓ Cache hit: {len(candles2)} candles (should be instant)")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    print("\n✅ Smoke test complete!")

if __name__ == "__main__":
    asyncio.run(main())
