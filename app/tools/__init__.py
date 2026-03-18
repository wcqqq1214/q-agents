"""Tool collection package for the finance agent."""

# Local database tools (preferred for Magnificent Seven)
from app.tools.local_tools import (
    get_local_stock_data,
    search_local_historical_news,
    search_realtime_news,
)

# Legacy MCP-based tools (for backward compatibility)
from app.tools.finance_tools import (
    get_stock_data,
    search_financial_news,
    search_news_with_duckduckgo,
    get_us_stock_quote,
    search_news_with_tavily,
    search_financial_news_tavily,
)

# Polymarket prediction market tools
from app.polymarket.tools import (
    search_polymarket_predictions,
    search_polymarket_by_category,
)

# Quant agent: use local database for historical data
QUANT_TOOLS = [get_local_stock_data]

# News agent: local historical + realtime search (via MCP with Tavily->DuckDuckGo fallback) + prediction markets
NEWS_TOOLS = [
    search_local_historical_news,
    search_realtime_news,  # Uses MCP server: Tavily first, falls back to DuckDuckGo
    search_polymarket_predictions,
    search_polymarket_by_category,
]

# Legacy single-agent bundle (MCP-based, for backward compatibility)
LEGACY_TOOLS = [get_us_stock_quote, search_news_with_duckduckgo, get_stock_data]

__all__ = [
    "get_local_stock_data",
    "search_local_historical_news",
    "search_realtime_news",
    "search_polymarket_predictions",
    "search_polymarket_by_category",
    "get_stock_data",
    "search_financial_news",
    "search_news_with_duckduckgo",
    "search_news_with_tavily",
    "search_financial_news_tavily",
    "get_us_stock_quote",
    "QUANT_TOOLS",
    "NEWS_TOOLS",
    "LEGACY_TOOLS",
]
