#!/bin/bash
# Start all services for the Finance Agent application

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Starting Finance Agent services..."

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Check and start MCP servers
if check_port 8000 || check_port 8001; then
    echo "MCP servers already running (ports 8000/8001 in use)"
else
    echo "Starting MCP servers..."
    bash "$SCRIPT_DIR/start_mcp_servers.sh"
fi

# Check and start FastAPI
if check_port 8080; then
    echo "FastAPI already running on port 8080"
else
    echo "Starting FastAPI backend..."
    bash "$SCRIPT_DIR/start_api.sh" &
    API_PID=$!
    sleep 2
fi

# Check and start frontend
if check_port 3000; then
    echo "Frontend already running on port 3000"
else
    echo "Starting Next.js frontend..."
    bash "$SCRIPT_DIR/start_frontend.sh" &
    FRONTEND_PID=$!
fi

echo ""
echo "All services started!"
echo "- Frontend: http://localhost:3000"
echo "- API: http://localhost:8080"
echo "- API Docs: http://localhost:8080/docs"
echo "- MCP Market Data: http://localhost:8000"
echo "- MCP News Search: http://localhost:8001"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for all background processes
wait
