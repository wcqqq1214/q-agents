#!/bin/bash
# Stop all MCP servers

echo "Stopping MCP Servers..."
ps aux | grep "mcp_servers/market_data/main.py" | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
ps aux | grep "mcp_servers/news_search/main.py" | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
echo "MCP Servers stopped."
