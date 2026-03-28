import logging
from datetime import datetime
from typing import List, Optional

from app.dataflows.base import (
    BaseDataProvider,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.dataflows.cache import CacheConfig, DataCache
from app.dataflows.config import DEFAULT_CONFIG
from app.dataflows.models import (
    NewsArticle,
    StockCandle,
)
from app.dataflows.providers.mcp_provider import MCPDataProvider
from app.dataflows.providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)

_PROVIDER_REGISTRY = {
    "mcp": MCPDataProvider,
    "yfinance": YFinanceProvider,
}


def validate_config(config: dict) -> None:
    """验证配置有效性"""
    for category, vendor in config.get("data_vendors", {}).items():
        if vendor not in _PROVIDER_REGISTRY:
            raise ValueError(
                f"Invalid vendor '{vendor}' for category '{category}'. "
                f"Available vendors: {list(_PROVIDER_REGISTRY.keys())}"
            )

    for tool_name, vendor in config.get("tool_vendors", {}).items():
        if vendor not in _PROVIDER_REGISTRY:
            raise ValueError(
                f"Invalid vendor '{vendor}' for tool '{tool_name}'. "
                f"Available vendors: {list(_PROVIDER_REGISTRY.keys())}"
            )


class DataFlowRouter:
    """带自动降级和缓存的数据路由器"""

    def __init__(self, config: dict = None, enable_cache: bool = True):
        self.config = config or DEFAULT_CONFIG
        validate_config(self.config)
        self._providers = {}
        self.cache = DataCache(self.config.get("redis_url")) if enable_cache else None

    def _get_provider(self, vendor_name: str) -> BaseDataProvider:
        """延迟加载提供商实例"""
        if vendor_name not in self._providers:
            provider_class = _PROVIDER_REGISTRY[vendor_name]
            self._providers[vendor_name] = provider_class(self.config)
        return self._providers[vendor_name]

    def _get_vendor_with_fallback(self, tool_name: str, category: str) -> tuple[str, Optional[str]]:
        """获取主提供商和备用提供商"""
        primary = self.config["tool_vendors"].get(tool_name)
        if not primary:
            primary = self.config["data_vendors"][category]

        fallback = None
        if primary == "mcp":
            fallback = "yfinance"
        elif primary == "yfinance":
            fallback = self.config.get("fallback_vendor")

        return primary, fallback

    async def _call_with_fallback(self, method_name: str, category: str, *args, **kwargs):
        """调用提供商方法，失败时自动降级"""
        primary_vendor, fallback_vendor = self._get_vendor_with_fallback(method_name, category)

        # 尝试主提供商
        try:
            provider = self._get_provider(primary_vendor)
            method = getattr(provider, method_name)
            result = await method(*args, **kwargs)
            logger.info(f"✓ {method_name} succeeded with {primary_vendor}")
            return result

        except (ProviderTimeoutError, ProviderRateLimitError, ProviderError) as e:
            logger.warning(f"✗ {method_name} failed with {primary_vendor}: {e}")

            if fallback_vendor:
                logger.info(f"↻ Falling back to {fallback_vendor}...")
                try:
                    fallback_provider = self._get_provider(fallback_vendor)
                    fallback_method = getattr(fallback_provider, method_name)
                    result = await fallback_method(*args, **kwargs)
                    logger.info(f"✓ {method_name} succeeded with fallback {fallback_vendor}")
                    return result
                except Exception as fallback_error:
                    logger.error(f"✗ Fallback {fallback_vendor} also failed: {fallback_error}")
                    raise fallback_error
            else:
                raise e

        except Exception as e:
            logger.error(f"✗ Unexpected error with {primary_vendor}: {type(e).__name__}: {e}")

            if fallback_vendor:
                logger.info(f"↻ Falling back to {fallback_vendor} due to unexpected error...")
                try:
                    fallback_provider = self._get_provider(fallback_vendor)
                    fallback_method = getattr(fallback_provider, method_name)
                    result = await fallback_method(*args, **kwargs)
                    logger.info(f"✓ {method_name} succeeded with fallback {fallback_vendor}")
                    return result
                except Exception as fallback_error:
                    logger.error(f"✗ Fallback {fallback_vendor} also failed: {fallback_error}")
                    raise fallback_error
            else:
                raise e

    async def get_stock_data(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[StockCandle]:
        """获取股票数据（带缓存和降级）"""
        if self.cache:
            cached = await self.cache.get(
                "stock_data",
                symbol=symbol,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )
            if cached:
                logger.info(f"✓ Cache hit for {symbol} stock data")
                return [StockCandle(**item) for item in cached]

        result = await self._call_with_fallback(
            "get_stock_data", "stock_data", symbol, start_date, end_date
        )

        if self.cache and result:
            await self.cache.set(
                "stock_data",
                result,
                CacheConfig.STOCK_DATA_TTL,
                symbol=symbol,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )

        return result

    async def get_news(
        self, query: str, limit: int = 10, start_date: Optional[datetime] = None
    ) -> List[NewsArticle]:
        """获取新闻（带缓存和降级）"""
        if self.cache:
            cached = await self.cache.get(
                "news",
                query=query,
                limit=limit,
                start=start_date.isoformat() if start_date else None,
            )
            if cached:
                return [NewsArticle(**item) for item in cached]

        result = await self._call_with_fallback("get_news", "news", query, limit, start_date)

        if self.cache and result:
            await self.cache.set(
                "news",
                result,
                CacheConfig.NEWS_TTL,
                query=query,
                limit=limit,
                start=start_date.isoformat() if start_date else None,
            )

        return result
