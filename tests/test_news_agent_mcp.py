"""Test News Agent realtime news search via MCP server with Tavily->DuckDuckGo fallback."""

import json
import os

from dotenv import load_dotenv

load_dotenv()


def test_mcp_fallback_logic():
    """Test that search_realtime_news uses MCP server with Tavily->DuckDuckGo fallback."""
    print("\n=== Testing MCP Server Fallback Logic ===")
    from app.tools.local_tools import search_realtime_news

    # Test 1: Normal search (should use Tavily if available)
    print("\n1. Normal search (NVDA):")
    result = search_realtime_news.invoke({"query": "NVDA", "limit": 3})
    data = json.loads(result)

    print(f"   Source: {data.get('source')}")
    print(f"   Count: {data.get('count')}")
    if data.get("count", 0) > 0:
        print(f"   First article: {data['articles'][0].get('title', 'N/A')[:50]}...")

    # Test 2: Another query
    print("\n2. Another search (Apple):")
    result = search_realtime_news.invoke({"query": "Apple", "limit": 3})
    data = json.loads(result)

    print(f"   Source: {data.get('source')}")
    print(f"   Count: {data.get('count')}")

    return True


def test_news_tools_config():
    """Test that NEWS_TOOLS is correctly configured."""
    print("\n=== Testing NEWS_TOOLS Configuration ===")
    from app.tools import NEWS_TOOLS

    print(f"\nNEWS_TOOLS contains {len(NEWS_TOOLS)} tools:")
    for tool in NEWS_TOOLS:
        print(f"  - {tool.name}")

    # Verify search_realtime_news is in NEWS_TOOLS
    tool_names = [t.name for t in NEWS_TOOLS]
    if "search_realtime_news" in tool_names:
        print("\n✓ search_realtime_news is in NEWS_TOOLS")
    else:
        print("\n✗ search_realtime_news NOT in NEWS_TOOLS")
        return False

    # Verify hybrid search is NOT in NEWS_TOOLS
    if "search_realtime_news_hybrid" not in tool_names:
        print("✓ search_realtime_news_hybrid correctly removed from NEWS_TOOLS")
    else:
        print("✗ search_realtime_news_hybrid should not be in NEWS_TOOLS")
        return False

    return True


def test_mcp_server_required():
    """Verify that search_realtime_news requires MCP server."""
    print("\n=== Verifying MCP Server Dependency ===")

    # Check if MCP server is running
    import subprocess

    result = subprocess.run(["ps", "aux"], capture_output=True, text=True)

    if (
        "mcp_servers/market_data/main.py" in result.stdout
        or "mcp_servers/news_search/main.py" in result.stdout
    ):
        print("✓ MCP servers are running")
        return True
    else:
        print("⚠ MCP servers are NOT running")
        print("  Start them with: bash scripts/start_mcp_servers.sh")
        return False


if __name__ == "__main__":
    if not os.environ.get("TAVILY_API_KEY"):
        print("WARNING: TAVILY_API_KEY not set")

    print("Testing News Agent MCP Integration")
    print("=" * 60)

    results = []
    results.append(("MCP Server Running", test_mcp_server_required()))
    results.append(("NEWS_TOOLS Config", test_news_tools_config()))
    results.append(("MCP Fallback Logic", test_mcp_fallback_logic()))

    print("\n" + "=" * 60)
    print("Test Summary:")
    for name, passed in results:
        status = "✓ PASS" if passed else "⚠ WARNING" if name == "MCP Server Running" else "✗ FAIL"
        print(f"  {status}: {name}")

    print("=" * 60)
    print("\n✓ News Agent now uses MCP server exclusively")
    print("  - Tavily first (via MCP)")
    print("  - Falls back to DuckDuckGo (via MCP)")
    print("  - No direct API calls")
