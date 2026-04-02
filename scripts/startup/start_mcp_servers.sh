#!/bin/bash
# Start all MCP servers

echo "Starting MCP servers from mcp_config.json..."
PYTHONPATH=/home/wcqqq21/q-agents uv run python -m app.mcp_client.cli start-all
echo ""
echo "To stop servers, run: bash scripts/startup/stop_mcp_servers.sh"
