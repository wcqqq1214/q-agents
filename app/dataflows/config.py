# app/dataflows/config.py
import os

from app.mcp_client.config import get_configured_mcp_server_base_urls

_MCP_SERVER_URLS = get_configured_mcp_server_base_urls()

DEFAULT_CONFIG = {
    # Data provider selection by category.
    "data_vendors": {
        "stock_data": "mcp",
        "technical_indicators": "mcp",
        "news": "mcp",
        "fundamentals": "yfinance",
    },
    # Optional tool-level overrides.
    "tool_vendors": {},
    # Fallback provider used when the primary vendor fails.
    "fallback_vendor": "yfinance",
    # MCP server base URLs.
    "mcp_servers": {
        "market_data": _MCP_SERVER_URLS.get("market_data", "http://localhost:8000"),
        "news_search": _MCP_SERVER_URLS.get("news_search", "http://localhost:8001"),
    },
    # Redis cache.
    "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
    # API keys.
    "api_keys": {
        "polygon": os.getenv("POLYGON_API_KEY"),
        "alpha_vantage": os.getenv("ALPHA_VANTAGE_API_KEY"),
    },
}
# Note: validate_config() will be defined in interface.py (Task 7) to avoid circular imports
