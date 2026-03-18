"""Simple integration test for Polymarket."""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.polymarket.client import PolymarketClient
from app.polymarket.tools import search_polymarket_predictions


def test_client():
    """Test Polymarket client."""
    print("=" * 60)
    print("Testing Polymarket Client")
    print("=" * 60)

    client = PolymarketClient()

    # Test fetching markets
    markets = client.fetch_markets(limit=5)
    print(f"\n✓ Fetched {len(markets)} markets from API")

    if markets:
        sample = markets[0]
        print(f"  Sample: {sample.get('question', 'N/A')[:70]}")

        # Test parsing
        parsed = client.parse_market_data(sample)
        print(f"  Parsed successfully:")
        print(f"    - Probability Yes: {parsed['probability_yes']:.1%}")
        print(f"    - Probability No: {parsed['probability_no']:.1%}")
        print(f"    - Volume 24h: ${parsed['volume_24h']:,.0f}")

    # Test search with different queries
    test_queries = ["Bitcoin", "Trump", "economy"]
    for query in test_queries:
        results = client.search_markets(query, limit=3)
        print(f"\n✓ Search '{query}': found {len(results)} markets")
        if results:
            print(f"  Top result: {results[0].get('question', 'N/A')[:60]}")


def test_tool():
    """Test LangChain tool."""
    print("\n" + "=" * 60)
    print("Testing LangChain Tool")
    print("=" * 60)

    queries = ["Bitcoin", "AI", "stock market"]

    for query in queries:
        print(f"\n--- Query: {query} ---")
        result = search_polymarket_predictions.invoke({"query": query, "limit": 3})
        data = json.loads(result)

        print(f"Markets found: {data['markets_found']}")

        for i, market in enumerate(data.get("markets", [])[:2], 1):
            print(f"\n{i}. {market['question'][:65]}")
            print(f"   Yes: {market['probability_yes']:.1%} | No: {market['probability_no']:.1%}")
            print(f"   Volume 24h: ${market['volume_24h']:,.0f}")
            print(f"   Category: {market.get('category') or 'N/A'}")


def test_tool_registration():
    """Test that tool is properly registered."""
    print("\n" + "=" * 60)
    print("Testing Tool Registration")
    print("=" * 60)

    from app.tools import NEWS_TOOLS, search_polymarket_predictions as imported_tool

    print(f"\n✓ NEWS_TOOLS contains {len(NEWS_TOOLS)} tools")
    print(f"  Tools: {[t.name for t in NEWS_TOOLS]}")

    if imported_tool in NEWS_TOOLS:
        print(f"✓ search_polymarket_predictions is registered in NEWS_TOOLS")
    else:
        print(f"✗ search_polymarket_predictions NOT found in NEWS_TOOLS")


if __name__ == "__main__":
    try:
        test_client()
        test_tool()
        test_tool_registration()
        print("\n" + "=" * 60)
        print("✅ All Polymarket integration tests passed!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
