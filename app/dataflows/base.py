# app/dataflows/base.py
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from app.dataflows.models import (
    FundamentalsData,
    NewsArticle,
    StockCandle,
    TechnicalIndicator,
)


class ProviderError(Exception):
    """数据提供商错误基类"""

    pass


class ProviderTimeoutError(ProviderError):
    """超时错误"""

    pass


class ProviderRateLimitError(ProviderError):
    """限流错误（429）"""

    pass


class BaseDataProvider(ABC):
    """所有数据提供商必须实现的异步接口"""

    def __init__(self, config: dict):
        self.config = config
        self.name = self.__class__.__name__

    @abstractmethod
    async def get_stock_data(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[StockCandle]:
        """获取 OHLCV 数据（异步）"""
        pass

    @abstractmethod
    async def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str],
        start_date: datetime,
        end_date: datetime,
    ) -> List[TechnicalIndicator]:
        """获取技术指标（异步）"""
        pass

    @abstractmethod
    async def get_news(
        self, query: str, limit: int = 10, start_date: Optional[datetime] = None
    ) -> List[NewsArticle]:
        """搜索新闻（异步）"""
        pass

    @abstractmethod
    async def get_fundamentals(self, symbol: str) -> FundamentalsData:
        """获取基本面数据（异步）"""
        pass

    async def health_check(self) -> bool:
        """健康检查（用于降级决策）"""
        try:
            return True
        except Exception:
            return False
