# app/dataflows/config.py
import os

DEFAULT_CONFIG = {
    # 数据提供商配置（类别级）
    "data_vendors": {
        "stock_data": "mcp",
        "technical_indicators": "mcp",
        "news": "mcp",
        "fundamentals": "yfinance",
    },
    # 工具级覆盖（可选）
    "tool_vendors": {},
    # 备用提供商（降级策略）
    "fallback_vendor": "yfinance",
    # MCP 服务器地址
    "mcp_servers": {
        "market_data": os.getenv("MCP_MARKET_DATA_URL", "http://localhost:8000"),
        "news_search": os.getenv("MCP_NEWS_SEARCH_URL", "http://localhost:8001"),
    },
    # Redis 缓存
    "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
    # API 密钥
    "api_keys": {
        "polygon": os.getenv("POLYGON_API_KEY"),
        "alpha_vantage": os.getenv("ALPHA_VANTAGE_API_KEY"),
    },
}
# Note: validate_config() will be defined in interface.py (Task 7) to avoid circular imports
