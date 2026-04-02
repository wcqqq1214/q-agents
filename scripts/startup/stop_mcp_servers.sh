#!/bin/bash
# Stop all MCP servers

echo "Stopping MCP Servers..."
ps aux | grep -E "mcp_servers/market_data/main.py|mcp_servers.market_data.main" | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
ps aux | grep -E "mcp_servers/news_search/main.py|mcp_servers.news_search.main" | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
echo "MCP Servers stopped."
