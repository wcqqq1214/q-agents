#!/bin/bash
# Start FastAPI from project root to ensure proper Python imports
# Proxy configuration is now handled by app/config/network.py

cd "$(dirname "$0")/.." && uv run uvicorn app.api.main:app --host 0.0.0.0 --port 8080 --reload
