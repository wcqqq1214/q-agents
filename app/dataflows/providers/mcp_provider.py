from datetime import datetime
from typing import List, Optional

import httpx

from app.dataflows.base import (
    BaseDataProvider,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.dataflows.models import (
    FundamentalsData,
    NewsArticle,
    StockCandle,
    TechnicalIndicator,
)


class MCPDataProvider(BaseDataProvider):
    """MCP 服务器适配器 - 负责数据标准化"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.market_data_url = config["mcp_servers"]["market_data"]
        self.news_search_url = config["mcp_servers"].get("news_search", "http://localhost:8001")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_stock_data(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[StockCandle]:
        """调用 MCP 服务器并标准化数据"""
        try:
            response = await self.client.post(
                f"{self.market_data_url}/mcp",
                json={
                    "tool": "get_historical_data",
                    "arguments": {
                        "symbol": symbol,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                    },
                },
            )
            response.raise_for_status()
            raw_data = response.json()

            # 标准化：将 MCP 返回的数据转换为 StockCandle
            candles = []
            for row in raw_data.get("data", []):
                candles.append(
                    StockCandle(
                        symbol=symbol,
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                    )
                )

            return candles

        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"MCP timeout: {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise ProviderRateLimitError(f"MCP rate limit: {e}")
            raise ProviderError(f"MCP HTTP error: {e}")
        except Exception as e:
            raise ProviderError(f"MCP error: {e}")

    async def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str],
        start_date: datetime,
        end_date: datetime,
    ) -> List[TechnicalIndicator]:
        """获取技术指标"""
        # TODO: Implement when MCP server supports indicators
        return []

    async def get_news(
        self, query: str, limit: int = 10, start_date: Optional[datetime] = None
    ) -> List[NewsArticle]:
        """搜索新闻"""
        try:
            response = await self.client.post(
                f"{self.news_search_url}/mcp",
                json={
                    "tool": "search_news",
                    "arguments": {"query": query, "limit": limit},
                },
            )
            response.raise_for_status()
            raw_data = response.json()

            articles = []
            for item in raw_data.get("articles", []):
                articles.append(
                    NewsArticle(
                        title=item["title"],
                        url=item["url"],
                        published_at=datetime.fromisoformat(item["published_at"]),
                        source=item["source"],
                        summary=item.get("summary"),
                    )
                )

            return articles

        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"MCP news timeout: {e}")
        except Exception as e:
            raise ProviderError(f"MCP news error: {e}")

    async def get_fundamentals(self, symbol: str) -> FundamentalsData:
        """获取基本面数据"""
        # TODO: Implement when needed
        raise NotImplementedError("MCP fundamentals not yet implemented")
