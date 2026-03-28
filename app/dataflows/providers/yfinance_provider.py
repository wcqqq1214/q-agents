# app/dataflows/providers/yfinance_provider.py
import asyncio
from datetime import datetime
from typing import List, Optional

import yfinance as yf

from app.dataflows.base import BaseDataProvider, ProviderError
from app.dataflows.models import (
    FundamentalsData,
    NewsArticle,
    StockCandle,
    TechnicalIndicator,
)


class YFinanceProvider(BaseDataProvider):
    """yfinance 适配器 - 负责数据标准化"""

    def __init__(self, config: dict):
        super().__init__(config)

    async def get_stock_data(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[StockCandle]:
        """调用 yfinance 并标准化数据（异步非阻塞）"""
        try:
            # 将同步阻塞操作封装到线程池
            def _fetch_data():
                ticker = yf.Ticker(symbol)
                return ticker.history(
                    start=start_date.strftime("%Y-%m-%d"),
                    end=end_date.strftime("%Y-%m-%d"),
                )

            # 在线程池中执行，释放事件循环
            df = await asyncio.to_thread(_fetch_data)

            if df.empty:
                return []

            # 标准化：将 yfinance DataFrame 转换为 StockCandle
            candles = []
            for timestamp, row in df.iterrows():
                candles.append(
                    StockCandle(
                        symbol=symbol,
                        timestamp=timestamp.to_pydatetime(),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=int(row["Volume"]),
                    )
                )

            return candles

        except Exception as e:
            raise ProviderError(f"yfinance error: {e}")

    async def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str],
        start_date: datetime,
        end_date: datetime,
    ) -> List[TechnicalIndicator]:
        """获取技术指标"""
        # TODO: Implement using stockstats or ta-lib
        return []

    async def get_news(
        self, query: str, limit: int = 10, start_date: Optional[datetime] = None
    ) -> List[NewsArticle]:
        """搜索新闻（异步非阻塞）"""
        try:
            # 将同步阻塞操作封装到线程池
            def _fetch_news():
                ticker = yf.Ticker(query)
                return ticker.news[:limit]

            # 在线程池中执行
            news = await asyncio.to_thread(_fetch_news)

            articles = []
            for item in news:
                articles.append(
                    NewsArticle(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        published_at=datetime.fromtimestamp(item.get("providerPublishTime", 0)),
                        source=item.get("publisher", ""),
                        summary=item.get("summary"),
                    )
                )

            return articles

        except Exception as e:
            raise ProviderError(f"yfinance news error: {e}")

    async def get_fundamentals(self, symbol: str) -> FundamentalsData:
        """获取基本面数据（异步非阻塞）"""
        try:
            # 将同步阻塞操作封装到线程池
            def _fetch_info():
                ticker = yf.Ticker(symbol)
                return ticker.info

            # 在线程池中执行
            info = await asyncio.to_thread(_fetch_info)

            return FundamentalsData(
                symbol=symbol,
                market_cap=info.get("marketCap"),
                pe_ratio=info.get("trailingPE"),
                eps=info.get("trailingEps"),
                revenue=info.get("totalRevenue"),
                profit_margin=info.get("profitMargins"),
                updated_at=datetime.now(),
            )

        except Exception as e:
            raise ProviderError(f"yfinance fundamentals error: {e}")
