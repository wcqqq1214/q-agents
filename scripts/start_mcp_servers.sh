#!/bin/bash
# Start all MCP servers

echo "Starting Market Data MCP Server..."
PYTHONPATH=/home/wcqqq21/finance-agent uv run python mcp_servers/market_data/main.py &
MARKET_DATA_PID=$!

echo "Starting News Search MCP Server..."
PYTHONPATH=/home/wcqqq21/finance-agent uv run python mcp_servers/news_search/main.py &
NEWS_SEARCH_PID=$!

echo "MCP Servers started:"
echo "  Market Data Server (PID: $MARKET_DATA_PID) - http://127.0.0.1:8000"
echo "  News Search Server (PID: $NEWS_SEARCH_PID) - http://127.0.0.1:8001"
echo ""
echo "To stop servers, run: bash scripts/stop_mcp_servers.sh"
