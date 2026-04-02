from datetime import UTC, datetime
from typing import List, Optional

from app.dataflows.base import (
    BaseDataProvider,
    ProviderError,
)
from app.dataflows.models import (
    FundamentalsData,
    NewsArticle,
    StockCandle,
    TechnicalIndicator,
)
from app.mcp_client.finance_client import (
    _call_get_stock_history_async,
    _call_search_news_async,
    _call_search_news_tavily_async,
)


class MCPDataProvider(BaseDataProvider):
    """MCP adapter responsible for normalizing provider output."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.market_data_url = config["mcp_servers"]["market_data"]
        self.news_search_url = config["mcp_servers"].get("news_search", "http://localhost:8001")

    async def get_stock_data(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[StockCandle]:
        """Fetch stock candles through MCP and normalize them."""
        try:
            raw_rows = await _call_get_stock_history_async(
                symbol,
                start_date.date().isoformat(),
                end_date.date().isoformat(),
                url=self.market_data_url,
            )

            candles: List[StockCandle] = []
            for row in raw_rows:
                if not isinstance(row, dict):
                    continue
                candles.append(
                    StockCandle(
                        symbol=symbol,
                        timestamp=datetime.fromisoformat(row["date"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row.get("volume") or 0),
                    )
                )

            return candles
        except Exception as exc:
            raise ProviderError(f"MCP error: {exc}") from exc

    async def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str],
        start_date: datetime,
        end_date: datetime,
    ) -> List[TechnicalIndicator]:
        """Fetch technical indicators."""
        # TODO: Implement when MCP server supports indicators
        return []

    async def get_news(
        self, query: str, limit: int = 10, start_date: Optional[datetime] = None
    ) -> List[NewsArticle]:
        """Fetch news articles through MCP."""
        try:
            normalized_start = None
            if start_date is not None:
                normalized_start = start_date if start_date.tzinfo else start_date.replace(tzinfo=UTC)

            try:
                raw_items = await _call_search_news_tavily_async(
                    query,
                    limit,
                    url=self.news_search_url,
                )
            except Exception:
                raw_items = await _call_search_news_async(
                    query,
                    limit,
                    url=self.news_search_url,
                )

            articles: List[NewsArticle] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue

                published_at = _parse_published_time(item.get("published_time"))
                if published_at is None:
                    continue
                if normalized_start is not None and published_at < normalized_start:
                    continue

                articles.append(
                    NewsArticle(
                        title=item.get("title") or "",
                        url=item.get("url") or "",
                        published_at=published_at,
                        source=item.get("source") or "unknown",
                        summary=item.get("snippet"),
                    )
                )

            return articles
        except Exception as exc:
            raise ProviderError(f"MCP news error: {exc}") from exc

    async def get_fundamentals(self, symbol: str) -> FundamentalsData:
        """Fetch fundamentals."""
        # TODO: Implement when needed
        raise NotImplementedError("MCP fundamentals not yet implemented")


def _parse_published_time(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
