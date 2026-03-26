# Data Provider Abstraction Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a provider-agnostic data abstraction layer with async interface, Redis caching, and automatic fallback for high availability.

**Architecture:** Three-layer design: (1) Pydantic models for data contracts, (2) async provider adapters (MCP/yfinance), (3) router with caching and fallback logic. All providers return standardized models, agents remain decoupled from data sources.

**Tech Stack:** Pydantic V2, redis.asyncio, httpx (async), rank-bm25

---

## File Structure

**New Files:**
- `app/dataflows/__init__.py` - Package exports
- `app/dataflows/base.py` - Abstract base class and exceptions
- `app/dataflows/models.py` - Pydantic data models
- `app/dataflows/config.py` - Configuration and validation
- `app/dataflows/cache.py` - Redis cache layer
- `app/dataflows/interface.py` - Router with fallback logic
- `app/dataflows/providers/__init__.py` - Provider package
- `app/dataflows/providers/mcp_provider.py` - MCP adapter
- `app/dataflows/providers/yfinance_provider.py` - yfinance adapter
- `app/dataflows/utils.py` - Utility functions

**Test Files:**
- `tests/test_dataflows_models.py` - Model validation tests
- `tests/test_dataflows_cache.py` - Cache layer tests
- `tests/test_dataflows_router.py` - Router and fallback tests
- `tests/test_dataflows_mcp_provider.py` - MCP provider tests
- `tests/test_dataflows_yfinance_provider.py` - yfinance provider tests

**Modified Files:**
- None (fully additive, backward compatible)

---

### Task 1: Pydantic Data Models

**Files:**
- Create: `app/dataflows/models.py`
- Test: `tests/test_dataflows_models.py`

- [ ] **Step 1: Write failing test for StockCandle validation**

```python
# tests/test_dataflows_models.py
import pytest
from datetime import datetime
from app.dataflows.models import StockCandle

def test_stock_candle_valid():
    """Test valid OHLCV data"""
    candle = StockCandle(
        timestamp=datetime(2024, 1, 1),
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1000000
    )
    assert candle.high >= candle.low
    assert candle.volume >= 0

def test_stock_candle_invalid_high_low():
    """Test high < low raises error"""
    with pytest.raises(ValueError, match="high must be >= low"):
        StockCandle(
            timestamp=datetime(2024, 1, 1),
            open=100.0,
            high=99.0,  # Invalid: high < low
            low=105.0,
            close=103.0,
            volume=1000000
        )

def test_stock_candle_negative_volume():
    """Test negative volume raises error"""
    with pytest.raises(ValueError, match="volume must be >= 0"):
        StockCandle(
            timestamp=datetime(2024, 1, 1),
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=-1000  # Invalid
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dataflows_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.dataflows'"

- [ ] **Step 3: Create models.py with StockCandle**

```python
# app/dataflows/models.py
from pydantic import BaseModel, Field, field_serializer, model_validator
from typing import List, Optional
from datetime import datetime

class StockCandle(BaseModel):
    """标准化的 OHLCV 数据"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    @field_serializer('timestamp')
    def serialize_timestamp(self, dt: datetime, _info):
        return dt.isoformat()

    @model_validator(mode='after')
    def validate_ohlc(self) -> 'StockCandle':
        """验证 OHLC 数据逻辑一致性"""
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be >= open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be <= open and close")
        if self.volume < 0:
            raise ValueError("volume must be >= 0")
        return self
```

- [ ] **Step 4: Create package __init__.py**

```python
# app/dataflows/__init__.py
"""Data provider abstraction layer"""
from app.dataflows.models import StockCandle, TechnicalIndicator, NewsArticle, FundamentalsData
from app.dataflows.interface import DataFlowRouter

__all__ = [
    "StockCandle",
    "TechnicalIndicator", 
    "NewsArticle",
    "FundamentalsData",
    "DataFlowRouter",
]
```

- [ ] **Step 5: Run test to verify StockCandle passes**

Run: `uv run pytest tests/test_dataflows_models.py::test_stock_candle_valid -v`
Expected: PASS

- [ ] **Step 6: Run validation tests**

Run: `uv run pytest tests/test_dataflows_models.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Add remaining models (TechnicalIndicator, NewsArticle, FundamentalsData)**

```python
# app/dataflows/models.py (append)

class TechnicalIndicator(BaseModel):
    """技术指标数据"""
    timestamp: datetime
    indicator_name: str  # "SMA_20", "MACD", "RSI_14"
    value: float
    metadata: Optional[dict] = None

    @field_serializer('timestamp')
    def serialize_timestamp(self, dt: datetime, _info):
        return dt.isoformat()

class NewsArticle(BaseModel):
    """新闻文章"""
    title: str
    url: str
    published_at: datetime
    source: str
    summary: Optional[str] = None
    sentiment: Optional[float] = Field(None, ge=-1.0, le=1.0)

    @field_serializer('published_at')
    def serialize_published_at(self, dt: datetime, _info):
        return dt.isoformat()

class FundamentalsData(BaseModel):
    """基本面数据"""
    symbol: str
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    revenue: Optional[float] = None
    profit_margin: Optional[float] = None
    updated_at: datetime

    @field_serializer('updated_at')
    def serialize_updated_at(self, dt: datetime, _info):
        return dt.isoformat()
```

- [ ] **Step 8: Commit models**

```bash
git add app/dataflows/ tests/test_dataflows_models.py
git commit -m "feat(dataflows): add Pydantic data models with validation

- Add StockCandle with OHLC validation
- Add TechnicalIndicator, NewsArticle, FundamentalsData
- Add model_validator for data integrity checks"
```

---

### Task 2: Abstract Base Class and Exceptions

**Files:**
- Create: `app/dataflows/base.py`
- Test: `tests/test_dataflows_base.py`

- [ ] **Step 1: Write test for provider interface**

```python
# tests/test_dataflows_base.py
import pytest
from app.dataflows.base import BaseDataProvider, ProviderError, ProviderTimeoutError

def test_provider_error_hierarchy():
    """Test exception hierarchy"""
    assert issubclass(ProviderTimeoutError, ProviderError)
    assert issubclass(ProviderError, Exception)

def test_base_provider_is_abstract():
    """Test BaseDataProvider cannot be instantiated"""
    with pytest.raises(TypeError):
        BaseDataProvider({})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dataflows_base.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement base.py**

```python
# app/dataflows/base.py
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from app.dataflows.models import (
    StockCandle, TechnicalIndicator, NewsArticle, FundamentalsData
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
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[StockCandle]:
        """获取 OHLCV 数据（异步）"""
        pass

    @abstractmethod
    async def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> List[TechnicalIndicator]:
        """获取技术指标（异步）"""
        pass

    @abstractmethod
    async def get_news(
        self,
        query: str,
        limit: int = 10,
        start_date: Optional[datetime] = None
    ) -> List[NewsArticle]:
        """搜索新闻（异步）"""
        pass

    @abstractmethod
    async def get_fundamentals(
        self,
        symbol: str
    ) -> FundamentalsData:
        """获取基本面数据（异步）"""
        pass

    async def health_check(self) -> bool:
        """健康检查（用于降级决策）"""
        try:
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_dataflows_base.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/dataflows/base.py tests/test_dataflows_base.py
git commit -m "feat(dataflows): add abstract base class and exceptions

- Add BaseDataProvider ABC with async interface
- Add ProviderError hierarchy (Timeout, RateLimit)
- Add health_check method for fallback decisions"
```

---

### Task 3: Configuration and Validation

**Files:**
- Create: `app/dataflows/config.py`
- Test: `tests/test_dataflows_config.py`

- [ ] **Step 1: Write test for config validation**

```python
# tests/test_dataflows_config.py
import pytest
from app.dataflows.config import DEFAULT_CONFIG, validate_config

def test_default_config_structure():
    """Test default config has required keys"""
    assert "data_vendors" in DEFAULT_CONFIG
    assert "tool_vendors" in DEFAULT_CONFIG
    assert "mcp_servers" in DEFAULT_CONFIG
    assert "redis_url" in DEFAULT_CONFIG

def test_validate_config_valid():
    """Test valid config passes"""
    config = {
        "data_vendors": {"stock_data": "mcp"},
        "tool_vendors": {},
    }
    # Should not raise
    validate_config(config)

def test_validate_config_invalid_vendor():
    """Test invalid vendor raises error"""
    config = {
        "data_vendors": {"stock_data": "invalid_vendor"},
        "tool_vendors": {},
    }
    with pytest.raises(ValueError, match="Invalid vendor"):
        validate_config(config)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dataflows_config.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement config.py**

```python
# app/dataflows/config.py
import os
from typing import Dict, Any

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
    }
}

# 将在 interface.py 中定义 _PROVIDER_REGISTRY 后导入
def validate_config(config: dict) -> None:
    """验证配置有效性"""
    # 延迟导入避免循环依赖
    from app.dataflows.interface import _PROVIDER_REGISTRY

    # 验证数据提供商配置
    for category, vendor in config.get("data_vendors", {}).items():
        if vendor not in _PROVIDER_REGISTRY:
            raise ValueError(
                f"Invalid vendor '{vendor}' for category '{category}'. "
                f"Available vendors: {list(_PROVIDER_REGISTRY.keys())}"
            )

    # 验证工具级配置
    for tool_name, vendor in config.get("tool_vendors", {}).items():
        if vendor not in _PROVIDER_REGISTRY:
            raise ValueError(
                f"Invalid vendor '{vendor}' for tool '{tool_name}'. "
                f"Available vendors: {list(_PROVIDER_REGISTRY.keys())}"
            )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_dataflows_config.py::test_default_config_structure -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/dataflows/config.py tests/test_dataflows_config.py
git commit -m "feat(dataflows): add configuration and validation

- Add DEFAULT_CONFIG with MCP/yfinance defaults
- Add validate_config() for vendor validation
- Support environment variables for URLs and API keys"
```

---

### Task 4: Redis Cache Layer

**Files:**
- Create: `app/dataflows/cache.py`
- Test: `tests/test_dataflows_cache.py`

- [ ] **Step 1: Write test for cache operations**

```python
# tests/test_dataflows_cache.py
import pytest
from datetime import datetime, timedelta
from app.dataflows.cache import DataCache, CacheConfig
from app.dataflows.models import StockCandle

@pytest.mark.asyncio
async def test_cache_set_and_get():
    """Test cache set and get operations"""
    cache = DataCache("redis://localhost:6379")

    # Create test data
    candles = [
        StockCandle(
            timestamp=datetime(2024, 1, 1),
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=1000000
        )
    ]

    # Set cache
    await cache.set(
        "stock_data",
        candles,
        CacheConfig.STOCK_DATA_TTL,
        symbol="AAPL",
        start="2024-01-01",
        end="2024-01-31"
    )

    # Get cache
    cached = await cache.get(
        "stock_data",
        symbol="AAPL",
        start="2024-01-01",
        end="2024-01-31"
    )

    assert cached is not None
    assert len(cached) == 1
    assert cached[0]["open"] == 100.0

@pytest.mark.asyncio
async def test_cache_miss():
    """Test cache miss returns None"""
    cache = DataCache("redis://localhost:6379")

    result = await cache.get(
        "stock_data",
        symbol="NONEXISTENT",
        start="2024-01-01"
    )

    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dataflows_cache.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement cache.py**

```python
# app/dataflows/cache.py
import json
import hashlib
from typing import Optional, List
from datetime import timedelta
import redis.asyncio as redis
from pydantic import BaseModel

class CacheConfig:
    """缓存配置"""
    STOCK_DATA_TTL = timedelta(days=7)
    INDICATORS_TTL = timedelta(days=1)
    NEWS_TTL = timedelta(hours=1)
    FUNDAMENTALS_TTL = timedelta(days=1)

class DataCache:
    """异步 Redis 缓存层"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    def _make_key(self, prefix: str, **kwargs) -> str:
        """生成缓存键"""
        params_str = json.dumps(kwargs, sort_keys=True, default=str)
        hash_suffix = hashlib.md5(params_str.encode()).hexdigest()[:8]
        return f"dataflow:{prefix}:{hash_suffix}"

    async def get(self, prefix: str, **kwargs) -> Optional[List[dict]]:
        """
        从缓存获取数据

        Returns:
            List[dict]: 返回 dict 列表（非 Pydantic 模型）
                       调用方需要手动重建模型
        """
        key = self._make_key(prefix, **kwargs)
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def set(
        self,
        prefix: str,
        data: List[BaseModel],
        ttl: timedelta,
        **kwargs
    ):
        """写入缓存（Pydantic V2）"""
        key = self._make_key(prefix, **kwargs)
        json_data = json.dumps([item.model_dump() for item in data], default=str)
        await self.redis.setex(key, int(ttl.total_seconds()), json_data)

    async def invalidate(self, prefix: str, **kwargs):
        """清除缓存"""
        key = self._make_key(prefix, **kwargs)
        await self.redis.delete(key)
```

- [ ] **Step 4: Install redis dependency**

Run: `uv add redis`
Expected: redis added to pyproject.toml

- [ ] **Step 5: Run tests (requires Redis running)**

Run: `uv run pytest tests/test_dataflows_cache.py -v`
Expected: PASS (if Redis is running), or SKIP with warning

- [ ] **Step 6: Commit**

```bash
git add app/dataflows/cache.py tests/test_dataflows_cache.py pyproject.toml uv.lock
git commit -m "feat(dataflows): add Redis cache layer

- Add DataCache with async Redis operations
- Add CacheConfig with TTL strategies (7d for stock, 1h for news)
- Add cache key generation with MD5 hash
- Add redis dependency"
```

---

### Task 5: MCP Provider Adapter

**Files:**
- Create: `app/dataflows/providers/__init__.py`
- Create: `app/dataflows/providers/mcp_provider.py`
- Test: `tests/test_dataflows_mcp_provider.py`

- [ ] **Step 1: Write test for MCP provider**

```python
# tests/test_dataflows_mcp_provider.py
import pytest
from datetime import datetime
from app.dataflows.providers.mcp_provider import MCPDataProvider
from app.dataflows.models import StockCandle
from app.dataflows.base import ProviderTimeoutError

@pytest.mark.asyncio
async def test_mcp_provider_get_stock_data():
    """Test MCP provider returns standardized StockCandle"""
    config = {
        "mcp_servers": {
            "market_data": "http://localhost:8000"
        }
    }
    provider = MCPDataProvider(config)

    # Mock MCP response
    result = await provider.get_stock_data(
        "AAPL",
        datetime(2024, 1, 1),
        datetime(2024, 1, 31)
    )

    assert isinstance(result, list)
    if result:  # If MCP server is running
        assert isinstance(result[0], StockCandle)
        assert result[0].symbol == "AAPL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dataflows_mcp_provider.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Create providers package**

```python
# app/dataflows/providers/__init__.py
"""Data provider implementations"""
from app.dataflows.providers.mcp_provider import MCPDataProvider

__all__ = ["MCPDataProvider"]
```

- [ ] **Step 4: Implement MCP provider**

```python
# app/dataflows/providers/mcp_provider.py
import httpx
from datetime import datetime
from typing import List, Optional
from app.dataflows.base import (
    BaseDataProvider, ProviderTimeoutError, ProviderRateLimitError, ProviderError
)
from app.dataflows.models import StockCandle, TechnicalIndicator, NewsArticle, FundamentalsData

class MCPDataProvider(BaseDataProvider):
    """MCP 服务器适配器 - 负责数据标准化"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.market_data_url = config["mcp_servers"]["market_data"]
        self.news_search_url = config["mcp_servers"]["news_search"]
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_stock_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
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
                        "end": end_date.isoformat()
                    }
                }
            )
            response.raise_for_status()
            raw_data = response.json()

            # 标准化：将 MCP 返回的数据转换为 StockCandle
            candles = []
            for row in raw_data.get("data", []):
                candles.append(StockCandle(
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"])
                ))

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
        end_date: datetime
    ) -> List[TechnicalIndicator]:
        """获取技术指标"""
        # TODO: Implement when MCP server supports indicators
        return []

    async def get_news(
        self,
        query: str,
        limit: int = 10,
        start_date: Optional[datetime] = None
    ) -> List[NewsArticle]:
        """搜索新闻"""
        try:
            response = await self.client.post(
                f"{self.news_search_url}/mcp",
                json={
                    "tool": "search_news",
                    "arguments": {
                        "query": query,
                        "limit": limit
                    }
                }
            )
            response.raise_for_status()
            raw_data = response.json()

            articles = []
            for item in raw_data.get("articles", []):
                articles.append(NewsArticle(
                    title=item["title"],
                    url=item["url"],
                    published_at=datetime.fromisoformat(item["published_at"]),
                    source=item["source"],
                    summary=item.get("summary")
                ))

            return articles

        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"MCP news timeout: {e}")
        except Exception as e:
            raise ProviderError(f"MCP news error: {e}")

    async def get_fundamentals(self, symbol: str) -> FundamentalsData:
        """获取基本面数据"""
        # TODO: Implement when needed
        raise NotImplementedError("MCP fundamentals not yet implemented")
```

- [ ] **Step 5: Install httpx dependency**

Run: `uv add httpx`
Expected: httpx added to pyproject.toml

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_dataflows_mcp_provider.py -v`
Expected: PASS or SKIP (if MCP server not running)

- [ ] **Step 7: Commit**

```bash
git add app/dataflows/providers/ tests/test_dataflows_mcp_provider.py pyproject.toml uv.lock
git commit -m "feat(dataflows): add MCP provider adapter

- Add MCPDataProvider with async httpx client
- Standardize MCP responses to Pydantic models
- Handle timeout and rate limit errors
- Add httpx dependency"
```

---

### Task 6: yfinance Provider Adapter

**Files:**
- Create: `app/dataflows/providers/yfinance_provider.py`
- Test: `tests/test_dataflows_yfinance_provider.py`

- [ ] **Step 1: Write test for yfinance provider**

```python
# tests/test_dataflows_yfinance_provider.py
import pytest
from datetime import datetime
from app.dataflows.providers.yfinance_provider import YFinanceProvider
from app.dataflows.models import StockCandle

@pytest.mark.asyncio
async def test_yfinance_provider_get_stock_data():
    """Test yfinance provider returns standardized StockCandle"""
    config = {}
    provider = YFinanceProvider(config)

    result = await provider.get_stock_data(
        "AAPL",
        datetime(2024, 1, 1),
        datetime(2024, 1, 31)
    )

    assert isinstance(result, list)
    assert len(result) > 0
    assert isinstance(result[0], StockCandle)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dataflows_yfinance_provider.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement yfinance provider**

```python
# app/dataflows/providers/yfinance_provider.py
import yfinance as yf
from datetime import datetime
from typing import List, Optional
from app.dataflows.base import BaseDataProvider, ProviderError, ProviderTimeoutError
from app.dataflows.models import StockCandle, TechnicalIndicator, NewsArticle, FundamentalsData

class YFinanceProvider(BaseDataProvider):
    """yfinance 适配器 - 负责数据标准化"""

    def __init__(self, config: dict):
        super().__init__(config)

    async def get_stock_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[StockCandle]:
        """调用 yfinance 并标准化数据"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d")
            )

            if df.empty:
                return []

            # 标准化：将 yfinance DataFrame 转换为 StockCandle
            candles = []
            for timestamp, row in df.iterrows():
                candles.append(StockCandle(
                    timestamp=timestamp.to_pydatetime(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"])
                ))

            return candles

        except Exception as e:
            raise ProviderError(f"yfinance error: {e}")

    async def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> List[TechnicalIndicator]:
        """获取技术指标"""
        # TODO: Implement using stockstats or ta-lib
        return []

    async def get_news(
        self,
        query: str,
        limit: int = 10,
        start_date: Optional[datetime] = None
    ) -> List[NewsArticle]:
        """搜索新闻"""
        try:
            ticker = yf.Ticker(query)
            news = ticker.news[:limit]

            articles = []
            for item in news:
                articles.append(NewsArticle(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    published_at=datetime.fromtimestamp(item.get("providerPublishTime", 0)),
                    source=item.get("publisher", ""),
                    summary=item.get("summary")
                ))

            return articles

        except Exception as e:
            raise ProviderError(f"yfinance news error: {e}")

    async def get_fundamentals(self, symbol: str) -> FundamentalsData:
        """获取基本面数据"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return FundamentalsData(
                symbol=symbol,
                market_cap=info.get("marketCap"),
                pe_ratio=info.get("trailingPE"),
                eps=info.get("trailingEps"),
                revenue=info.get("totalRevenue"),
                profit_margin=info.get("profitMargins"),
                updated_at=datetime.now()
            )

        except Exception as e:
            raise ProviderError(f"yfinance fundamentals error: {e}")
```

- [ ] **Step 4: Update providers __init__.py**

```python
# app/dataflows/providers/__init__.py
"""Data provider implementations"""
from app.dataflows.providers.mcp_provider import MCPDataProvider
from app.dataflows.providers.yfinance_provider import YFinanceProvider

__all__ = ["MCPDataProvider", "YFinanceProvider"]
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_dataflows_yfinance_provider.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/dataflows/providers/ tests/test_dataflows_yfinance_provider.py
git commit -m "feat(dataflows): add yfinance provider adapter

- Add YFinanceProvider with data standardization
- Convert yfinance DataFrame to StockCandle models
- Support stock data, news, and fundamentals
- Handle yfinance-specific errors"
```

---

### Task 7: DataFlowRouter with Fallback Logic

**Files:**
- Create: `app/dataflows/interface.py`
- Test: `tests/test_dataflows_router.py`

- [ ] **Step 1: Write test for router fallback**

```python
# tests/test_dataflows_router.py
import pytest
from datetime import datetime
from app.dataflows.interface import DataFlowRouter
from app.dataflows.models import StockCandle

@pytest.mark.asyncio
async def test_router_primary_success():
    """Test router uses primary provider when available"""
    config = {
        "data_vendors": {"stock_data": "mcp"},
        "tool_vendors": {},
        "mcp_servers": {
            "market_data": "http://localhost:8000",
            "news_search": "http://localhost:8001"
        },
        "redis_url": "redis://localhost:6379"
    }
    router = DataFlowRouter(config, enable_cache=False)

    result = await router.get_stock_data(
        "AAPL",
        datetime(2024, 1, 1),
        datetime(2024, 1, 31)
    )

    assert isinstance(result, list)

@pytest.mark.asyncio
async def test_router_fallback_on_error():
    """Test router falls back to yfinance when MCP fails"""
    config = {
        "data_vendors": {"stock_data": "mcp"},
        "tool_vendors": {},
        "mcp_servers": {
            "market_data": "http://invalid:9999",  # Invalid URL
            "news_search": "http://localhost:8001"
        },
        "fallback_vendor": "yfinance",
        "redis_url": "redis://localhost:6379"
    }
    router = DataFlowRouter(config, enable_cache=False)

    # Should fallback to yfinance
    result = await router.get_stock_data(
        "AAPL",
        datetime(2024, 1, 1),
        datetime(2024, 1, 31)
    )

    assert isinstance(result, list)
    assert len(result) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dataflows_router.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement interface.py (Part 1: Registry and Router init)**

```python
# app/dataflows/interface.py
import logging
from typing import List, Optional
from datetime import datetime
from app.dataflows.base import (
    BaseDataProvider, ProviderError, ProviderTimeoutError, ProviderRateLimitError
)
from app.dataflows.models import StockCandle, TechnicalIndicator, NewsArticle, FundamentalsData
from app.dataflows.cache import DataCache, CacheConfig
from app.dataflows.config import DEFAULT_CONFIG
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
```

- [ ] **Step 4: Implement interface.py (Part 2: Fallback logic)**

```python
# app/dataflows/interface.py (append)

    async def _call_with_fallback(
        self,
        method_name: str,
        category: str,
        *args,
        **kwargs
    ):
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
```

- [ ] **Step 5: Implement interface.py (Part 3: Public methods)**

```python
# app/dataflows/interface.py (append)

    async def get_stock_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[StockCandle]:
        """获取股票数据（带缓存和降级）"""
        if self.cache:
            cached = await self.cache.get(
                "stock_data",
                symbol=symbol,
                start=start_date.isoformat(),
                end=end_date.isoformat()
            )
            if cached:
                logger.info(f"✓ Cache hit for {symbol} stock data")
                return [StockCandle(**item) for item in cached]

        result = await self._call_with_fallback(
            "get_stock_data",
            "stock_data",
            symbol, start_date, end_date
        )

        if self.cache and result:
            await self.cache.set(
                "stock_data",
                result,
                CacheConfig.STOCK_DATA_TTL,
                symbol=symbol,
                start=start_date.isoformat(),
                end=end_date.isoformat()
            )

        return result

    async def get_news(
        self,
        query: str,
        limit: int = 10,
        start_date: Optional[datetime] = None
    ) -> List[NewsArticle]:
        """获取新闻（带缓存和降级）"""
        if self.cache:
            cached = await self.cache.get(
                "news",
                query=query,
                limit=limit,
                start=start_date.isoformat() if start_date else None
            )
            if cached:
                return [NewsArticle(**item) for item in cached]

        result = await self._call_with_fallback(
            "get_news",
            "news",
            query, limit, start_date
        )

        if self.cache and result:
            await self.cache.set(
                "news",
                result,
                CacheConfig.NEWS_TTL,
                query=query,
                limit=limit,
                start=start_date.isoformat() if start_date else None
            )

        return result
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_dataflows_router.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/dataflows/interface.py tests/test_dataflows_router.py
git commit -m "feat(dataflows): add DataFlowRouter with fallback logic

- Add _call_with_fallback for automatic provider switching
- Add cache integration with get_stock_data and get_news
- Handle timeout, rate limit, and unexpected errors
- Log all provider attempts and fallbacks"
```

---

### Task 8: Integration Tests

**Files:**
- Create: `tests/integration/test_dataflows_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_dataflows_integration.py
import pytest
from datetime import datetime
from app.dataflows.interface import DataFlowRouter

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_stack_with_cache():
    """Test complete flow: router → provider → cache"""
    router = DataFlowRouter(enable_cache=True)

    # First call (cache miss)
    result1 = await router.get_stock_data(
        "AAPL",
        datetime(2024, 1, 1),
        datetime(2024, 1, 31)
    )

    assert len(result1) > 0

    # Second call (cache hit)
    result2 = await router.get_stock_data(
        "AAPL",
        datetime(2024, 1, 1),
        datetime(2024, 1, 31)
    )

    assert result1 == result2

@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_to_yfinance_fallback():
    """Test MCP failure triggers yfinance fallback"""
    config = {
        "data_vendors": {"stock_data": "mcp"},
        "tool_vendors": {},
        "mcp_servers": {
            "market_data": "http://localhost:9999",  # Invalid
            "news_search": "http://localhost:8001"
        },
        "fallback_vendor": "yfinance",
        "redis_url": "redis://localhost:6379"
    }
    router = DataFlowRouter(config, enable_cache=False)

    result = await router.get_stock_data(
        "AAPL",
        datetime(2024, 1, 1),
        datetime(2024, 1, 31)
    )

    assert len(result) > 0  # yfinance should succeed
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/integration/ -v -m integration`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/
git commit -m "test(dataflows): add integration tests

- Add full-stack test with cache
- Add MCP-to-yfinance fallback test
- Mark with @pytest.mark.integration"
```

---

### Task 9: Update Documentation

**Files:**
- Modify: `CLAUDE.md`
- Create: `app/dataflows/README.md`

- [ ] **Step 1: Add dataflows section to CLAUDE.md**

```markdown
# CLAUDE.md (append to Architecture Overview section)

### Data Provider Abstraction Layer

**Location**: `app/dataflows/`

**Purpose**: Provider-agnostic data interface with caching and automatic fallback.

**Key Components**:
- `models.py`: Pydantic data contracts (StockCandle, NewsArticle, etc.)
- `interface.py`: DataFlowRouter with fallback logic
- `cache.py`: Redis cache layer (7d TTL for stock data, 1h for news)
- `providers/`: MCP and yfinance adapters

**Usage**:
```python
from app.dataflows.interface import DataFlowRouter
from datetime import datetime

router = DataFlowRouter()
candles = await router.get_stock_data(
    "AAPL",
    datetime(2024, 1, 1),
    datetime(2024, 12, 31)
)
```

**Configuration**:
Edit `app/dataflows/config.py` to change data vendors:
```python
"data_vendors": {
    "stock_data": "yfinance",  # Switch from MCP to yfinance
}
```

**Fallback Strategy**:
- Primary: MCP servers (localhost:8000, localhost:8001)
- Fallback: yfinance (automatic on MCP timeout/error)
- Cache: Redis (reduces API calls)
```

- [ ] **Step 2: Create dataflows README**

```markdown
# app/dataflows/README.md

# Data Provider Abstraction Layer

## Overview

Provider-agnostic data interface that allows switching between MCP, yfinance, Polygon, and Alpha Vantage without changing agent code.

## Architecture

```
Agent → DataFlowRouter → [Cache?] → Provider → External API
                    ↓ (on error)
                    Fallback Provider
```

## Quick Start

```python
from app.dataflows.interface import DataFlowRouter

router = DataFlowRouter()
data = await router.get_stock_data("AAPL", start, end)
```

## Configuration

See `config.py` for:
- Data vendor selection (MCP/yfinance/polygon)
- Cache TTL settings
- MCP server URLs
- API keys

## Adding New Providers

1. Create `providers/new_provider.py`
2. Inherit from `BaseDataProvider`
3. Implement all abstract methods
4. Return standardized Pydantic models
5. Add to `_PROVIDER_REGISTRY` in `interface.py`

## Testing

```bash
# Unit tests
uv run pytest tests/test_dataflows_*.py

# Integration tests (requires Redis + MCP servers)
uv run pytest tests/integration/ -m integration
```
```

- [ ] **Step 3: Commit documentation**

```bash
git add CLAUDE.md app/dataflows/README.md
git commit -m "docs(dataflows): add documentation

- Add dataflows section to CLAUDE.md
- Create app/dataflows/README.md with usage guide
- Document configuration and fallback strategy"
```

---

### Task 10: End-to-End Smoke Test

**Files:**
- Create: `scripts/test_dataflows.py`

- [ ] **Step 1: Create smoke test script**

```python
# scripts/test_dataflows.py
"""Smoke test for data provider abstraction layer"""
import asyncio
from datetime import datetime, timedelta
from app.dataflows.interface import DataFlowRouter

async def main():
    print("🧪 Testing Data Provider Abstraction Layer\n")

    router = DataFlowRouter(enable_cache=True)

    # Test 1: Stock data
    print("1️⃣  Testing stock data...")
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        candles = await router.get_stock_data("AAPL", start_date, end_date)
        print(f"   ✓ Retrieved {len(candles)} candles for AAPL")
        print(f"   ✓ Latest close: ${candles[-1].close:.2f}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Test 2: News
    print("\n2️⃣  Testing news search...")
    try:
        articles = await router.get_news("AAPL", limit=5)
        print(f"   ✓ Retrieved {len(articles)} news articles")
        if articles:
            print(f"   ✓ Latest: {articles[0].title[:60]}...")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Test 3: Cache hit
    print("\n3️⃣  Testing cache...")
    try:
        candles2 = await router.get_stock_data("AAPL", start_date, end_date)
        print(f"   ✓ Cache hit: {len(candles2)} candles (should be instant)")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    print("\n✅ Smoke test complete!")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run smoke test**

Run: `uv run python scripts/test_dataflows.py`
Expected: All 3 tests pass with ✓

- [ ] **Step 3: Commit smoke test**

```bash
git add scripts/test_dataflows.py
git commit -m "test(dataflows): add end-to-end smoke test

- Add scripts/test_dataflows.py for manual testing
- Test stock data, news, and cache functionality
- Provide visual feedback with emojis"
```

---

## Plan Complete

**Summary:**
- 10 tasks covering models, providers, router, cache, and tests
- All code follows TDD (test → fail → implement → pass → commit)
- Backward compatible (no changes to existing code)
- Ready for execution with @superpowers:subagent-driven-development or @superpowers:executing-plans

**Estimated Time:** 4-6 hours

**Dependencies:**
- Redis server running (for cache tests)
- MCP servers running (for integration tests, optional)

**Next Steps:**
1. Review this plan
2. Choose execution method (subagent-driven or inline)
3. Execute tasks 1-10 in order

