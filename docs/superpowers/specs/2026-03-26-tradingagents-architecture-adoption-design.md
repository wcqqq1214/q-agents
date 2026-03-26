---
name: TradingAgents 架构借鉴与改进方案
description: 从 TradingAgents 项目借鉴数据提供商抽象层、LLM 工厂模式和 BM25 记忆系统的渐进式改进设计
type: architecture
date: 2026-03-26
---

# TradingAgents 架构借鉴与改进方案

## 1. 概述

### 1.1 背景

TradingAgents 是一个高 star 的多智能体金融交易框架，与我们的 finance-agent 项目在架构上有诸多相似之处。通过分析其设计模式，我们识别出三个可以借鉴的核心架构：

1. **数据提供商抽象层**：供应商无关的数据接口，支持配置级切换
2. **LLM 提供商工厂模式**：统一的 LLM 客户端接口，支持多提供商
3. **BM25 离线记忆系统**：无 API 调用的关键词检索记忆

### 1.2 改进策略

采用**渐进式改进**方案（方案 A）：
- 保持现有 MCP 架构和 LangGraph 编排不变
- 引入低风险、高价值的基础设施改进
- 实施周期：1-2 周
- 风险等级：低

### 1.3 核心设计原则

1. **向后兼容**：现有代码继续工作，新功能通过配置开启
2. **MCP 优先**：保留 MCP 服务器作为主要数据源
3. **配置驱动**：所有切换通过配置文件，不改代码
4. **渐进迁移**：可以逐个 agent 迁移到新抽象层

## 2. 整体架构设计

### 2.1 架构层次

```
┌─────────────────────────────────────────────────┐
│  Agent Layer (Quant/News/Social/CIO)           │
│  - 保持现有 agent 逻辑不变                        │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  NEW: Data Provider Abstraction                 │
│  - 统一接口：get_stock_data(), get_news()等      │
│  - 配置驱动：config["data_vendors"]              │
│  - 支持：MCP/yfinance/Polygon/Alpha Vantage     │
│  - 运行时降级：MCP 失败自动切换 yfinance          │
│  - Redis 缓存：历史数据 7 天 TTL                 │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  NEW: LLM Provider Factory                      │
│  - 工厂函数：create_llm(provider, model)         │
│  - 支持：OpenAI/Anthropic/Google                │
│  - 提供商特定配置：reasoning_effort/thinking等   │
│  - Agent 专用优化：Quant 用推理模型              │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  NEW: BM25 Memory System                        │
│  - 离线检索，无 API 调用                          │
│  - 存储历史决策和反思                             │
│  - 补充现有 ChromaDB RAG                         │
│  - 混合检索：BM25 + ChromaDB RRF 融合           │
└─────────────────────────────────────────────────┘
```

### 2.2 与现有架构的关系

**保持不变**：
- LangGraph 多 agent 编排（`app/graph_multi.py`）
- MCP 服务器（`mcp_servers/market_data/`, `mcp_servers/news_search/`）
- FastAPI 后端和 Next.js 前端
- ChromaDB RAG 系统

**新增模块**：
- `app/dataflows/` - 数据提供商抽象层
- `app/llm_clients/` - LLM 提供商工厂
- `app/memory/` - BM25 记忆系统

**重构模块**：
- `app/llm_config.py` → 迁移到工厂模式
- `app/tools/finance_tools.py` → 通过抽象层调用

### 2.3 实施路线图

**阶段 1（第 1 周）**：
1. 实现数据提供商抽象层基础框架
2. 实现 MCP 和 yfinance 适配器
3. 集成 Redis 缓存层

**阶段 2（第 2 周）**：
1. 实现 LLM 提供商工厂模式
2. 重构现有 `llm_config.py`
3. 配置 Agent 专用模型

**阶段 3（第 2 周）**：
1. 实现 BM25 记忆系统
2. 实现混合检索（BM25 + ChromaDB）
3. 集成到 CIO Agent


## 3. 数据提供商抽象层设计

### 3.1 目录结构

```
app/dataflows/
├── __init__.py
├── base.py              # 异步 ABC 抽象基类
├── models.py            # Pydantic 数据模型（标准化契约）
├── config.py            # 配置管理
├── interface.py         # 带降级和缓存的路由器
├── cache.py             # Redis 缓存层
├── providers/
│   ├── __init__.py
│   ├── mcp_provider.py      # MCP 服务器适配器（主要）
│   ├── yfinance_provider.py # yfinance 直接调用
│   ├── polygon_provider.py  # Polygon API
│   └── alpha_vantage_provider.py
└── utils.py
```

### 3.2 Pydantic 数据模型（标准化契约）

**核心思想**：所有数据提供商必须返回标准化的 Pydantic 模型，Agent 层完全不关心底层数据源格式。

**`app/dataflows/models.py`**：

```python
from pydantic import BaseModel, Field, field_serializer, model_validator
from typing import List, Optional
from datetime import datetime
from enum import Enum

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

class TechnicalIndicator(BaseModel):
    """技术指标数据"""
    timestamp: datetime
    indicator_name: str  # "SMA_20", "MACD", "RSI_14"
    value: float
    metadata: Optional[dict] = None  # 额外信息（如 MACD 的 signal line）
    
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
    sentiment: Optional[float] = Field(None, ge=-1.0, le=1.0)  # -1 到 1
    
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

**关键优势**：
- yfinance 返回的 `Open/High/Low/Close` 和 Polygon 返回的 `o/h/l/c` 都被标准化为 `open/high/low/close`
- 时间戳格式统一为 `datetime` 对象
- Agent 层代码完全解耦，不受数据源变化影响

### 3.3 异步抽象基类

**`app/dataflows/base.py`**：

```python
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
        """
        获取 OHLCV 数据（异步）
        
        必须返回标准化的 StockCandle 列表
        提供商负责将原始数据转换为标准格式
        """
        pass
    
    @abstractmethod
    async def get_technical_indicators(
        self, 
        symbol: str, 
        indicators: List[str],  # ["SMA_20", "MACD", "RSI_14"]
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

**关键特性**：
- 全异步接口（`async def`），支持高并发
- 返回类型强制为 Pydantic 模型
- 定义了三种异常类型，用于降级决策


### 3.4 Redis 缓存层

**`app/dataflows/cache.py`**：

```python
import json
import hashlib
from typing import Optional, Any, List
from datetime import timedelta
import redis.asyncio as redis
from pydantic import BaseModel

class CacheConfig:
    """缓存配置"""
    # 历史数据：长 TTL（7 天）
    STOCK_DATA_TTL = timedelta(days=7)
    # 技术指标：中等 TTL（1 天）
    INDICATORS_TTL = timedelta(days=1)
    # 新闻：短 TTL（1 小时）
    NEWS_TTL = timedelta(hours=1)
    # 基本面：中等 TTL（1 天）
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
                       调用方需要手动重建模型：[Model(**item) for item in cached]
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

**缓存策略**：
- 历史数据（OHLCV）：7 天 TTL，因为历史数据不会变化
- 技术指标：1 天 TTL，每日收盘后重新计算
- 新闻：1 小时 TTL，新闻时效性强
- 基本面：1 天 TTL，财报数据更新频率低

### 3.5 带降级和缓存的路由器

**`app/dataflows/interface.py`**：

```python
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
from app.dataflows.providers.polygon_provider import PolygonProvider

logger = logging.getLogger(__name__)

_PROVIDER_REGISTRY = {
    "mcp": MCPDataProvider,
    "yfinance": YFinanceProvider,
    "polygon": PolygonProvider,
}

def validate_config(config: dict) -> None:
    """验证配置有效性"""
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

class DataFlowRouter:
    """
    带自动降级和缓存的数据路由器

    特性：
    1. 运行时异常自动降级到备用数据源
    2. Redis 缓存层（历史数据长 TTL）
    3. 异步接口支持高并发
    """

    def __init__(self, config: dict = None, enable_cache: bool = True):
        self.config = config or DEFAULT_CONFIG
        # 验证配置
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
        """
        获取主提供商和备用提供商
        
        Returns:
            (primary_vendor, fallback_vendor)
        """
        # 1. 工具级配置
        primary = self.config["tool_vendors"].get(tool_name)
        # 2. 类别级配置
        if not primary:
            primary = self.config["data_vendors"][category]
        
        # 3. 确定备用提供商
        fallback = None
        if primary == "mcp":
            fallback = "yfinance"
        elif primary == "yfinance":
            fallback = self.config.get("fallback_vendor", "polygon")
        
        return primary, fallback
    
    async def _call_with_fallback(
        self,
        method_name: str,
        category: str,
        *args,
        **kwargs
    ):
        """
        调用提供商方法，失败时自动降级
        """
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

            # 如果有备用提供商，尝试降级
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
            # 捕获所有其他未预期的异常
            logger.error(f"✗ Unexpected error with {primary_vendor}: {type(e).__name__}: {e}")

            # 尝试降级
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
        self, 
        symbol: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> List[StockCandle]:
        """获取股票数据（带缓存和降级）"""
        # 1. 尝试从缓存读取
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
        
        # 2. 缓存未命中，调用提供商（带降级）
        result = await self._call_with_fallback(
            "get_stock_data",
            "stock_data",
            symbol, start_date, end_date
        )
        
        # 3. 写入缓存
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
    
    # get_technical_indicators, get_news, get_fundamentals 类似实现...
```

**关键特性**：
1. **运行时降级**：MCP 超时自动切换 yfinance，对用户透明
2. **智能缓存**：历史数据 7 天 TTL，新闻 1 小时 TTL
3. **异步高并发**：支持并发获取多只股票数据
4. **日志追踪**：每次调用记录提供商和结果


## 4. LLM 提供商工厂模式设计

### 4.1 目录结构

```
app/llm_clients/
├── __init__.py
├── base.py              # ABC 抽象基类
├── factory.py           # 工厂函数
├── config.py            # LLM 配置
├── providers/
│   ├── __init__.py
│   ├── openai_client.py
│   ├── anthropic_client.py
│   └── google_client.py
└── utils.py
```

### 4.2 抽象基类

**`app/llm_clients/base.py`**：

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List, Type
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

class BaseLLMClient(ABC):
    """所有 LLM 提供商必须实现的接口"""
    
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        streaming: bool = True,
        max_retries: int = 3,
        temperature: float = 0.7,
        **kwargs
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.streaming = streaming
        self.max_retries = max_retries
        self.temperature = temperature
        self.extra_kwargs = kwargs
    
    @abstractmethod
    def get_llm(self) -> BaseChatModel:
        """返回 LangChain 兼容的 LLM 实例"""
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """返回提供商名称（用于日志）"""
        pass
    
    def get_structured_llm(self, schema: Type[BaseModel]) -> BaseChatModel:
        """
        返回绑定了结构化输出的 LLM 实例
        
        子类可以覆盖此方法来处理提供商特定的结构化输出问题
        """
        llm = self.get_llm()
        return llm.with_structured_output(schema)
    
    def supports_streaming(self) -> bool:
        """是否支持流式输出"""
        return True
    
    def _filter_unsupported_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """过滤模型不支持的参数（子类可覆盖）"""
        return params
```

### 4.3 OpenAI 客户端（支持 o 系列特殊处理）

**`app/llm_clients/providers/openai_client.py`**：

```python
import os
import logging
from typing import Optional, Dict, Any, Type
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from app.llm_clients.base import BaseLLMClient

logger = logging.getLogger(__name__)

class OpenAIClient(BaseLLMClient):
    """OpenAI LLM 客户端（支持 o 系列特殊处理）"""
    
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        reasoning_effort: Optional[str] = None,  # "low", "medium", "high"
        **kwargs
    ):
        super().__init__(model, api_key, base_url, **kwargs)
        self.reasoning_effort = reasoning_effort
        self._is_o_series = model.startswith(("o1", "o3"))
    
    def _filter_unsupported_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        o 系列模型特殊处理：
        - 不支持 temperature（固定为 1）
        - 不支持 streaming
        - 不支持 max_tokens（使用 max_completion_tokens）
        """
        if self._is_o_series:
            filtered = params.copy()
            
            if "temperature" in filtered:
                logger.warning(f"Model {self.model} does not support temperature, removing...")
                filtered.pop("temperature")
            
            if "streaming" in filtered:
                logger.warning(f"Model {self.model} does not support streaming, disabling...")
                filtered["streaming"] = False
            
            if "max_tokens" in filtered:
                filtered["max_completion_tokens"] = filtered.pop("max_tokens")
            
            return filtered
        
        return params
    
    def get_llm(self) -> ChatOpenAI:
        """返回 LangChain ChatOpenAI 实例"""
        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        
        llm_kwargs = {
            "model": self.model,
            "api_key": api_key,
            "temperature": self.temperature,
            "streaming": self.streaming,
            "max_retries": self.max_retries,
        }
        
        if self.base_url:
            llm_kwargs["base_url"] = self.base_url
        
        # o 系列支持 reasoning_effort
        if self.reasoning_effort and self._is_o_series:
            llm_kwargs["model_kwargs"] = {
                "reasoning_effort": self.reasoning_effort
            }
        
        # 过滤不支持的参数
        llm_kwargs = self._filter_unsupported_params(llm_kwargs)
        
        return ChatOpenAI(**llm_kwargs)
    
    def supports_streaming(self) -> bool:
        """o 系列不支持流式输出"""
        return not self._is_o_series
    
    def get_structured_llm(self, schema: Type[BaseModel]) -> ChatOpenAI:
        """OpenAI 的结构化输出使用 Native JSON Schema"""
        llm = self.get_llm()
        try:
            return llm.with_structured_output(schema, method="json_schema")
        except Exception as e:
            logger.warning(f"json_schema method failed, falling back to json_mode: {e}")
            return llm.with_structured_output(schema, method="json_mode")
    
    def get_provider_name(self) -> str:
        return "OpenAI"
```

### 4.4 Anthropic 客户端

**`app/llm_clients/providers/anthropic_client.py`**：

```python
import os
import logging
from typing import Optional, Dict, Any, Type
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel
from app.llm_clients.base import BaseLLMClient

logger = logging.getLogger(__name__)

class AnthropicClient(BaseLLMClient):
    """Anthropic Claude 客户端"""
    
    def __init__(
        self,
        model: str = "claude-opus-4-6",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        extended_thinking: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        super().__init__(model, api_key, base_url, **kwargs)
        self.extended_thinking = extended_thinking
    
    def get_llm(self) -> ChatAnthropic:
        """返回 LangChain ChatAnthropic 实例"""
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        
        llm_kwargs = {
            "model": self.model,
            "anthropic_api_key": api_key,
            "temperature": self.temperature,
            "streaming": self.streaming,
            "max_retries": self.max_retries,
        }
        
        # Claude 4.6+ 支持 extended thinking
        if self.extended_thinking and self.extended_thinking.get("enabled"):
            llm_kwargs["model_kwargs"] = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": self.extended_thinking.get("budget_tokens", 10000)
                }
            }
        
        return ChatAnthropic(**llm_kwargs)
    
    def get_structured_llm(self, schema: Type[BaseModel]) -> ChatAnthropic:
        """
        Anthropic 的结构化输出处理
        
        使用 tool calling（更可靠），失败时回退到 JSON mode
        """
        llm = self.get_llm()
        
        try:
            return llm.with_structured_output(schema, method="function_calling")
        except Exception as e:
            logger.warning(f"Function calling failed, falling back to JSON mode: {e}")
            return llm.with_structured_output(schema, method="json_mode")
    
    def get_provider_name(self) -> str:
        return "Anthropic"
```

### 4.5 Google 客户端

**`app/llm_clients/providers/google_client.py`**：

```python
import os
from typing import Optional, Type
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel
from app.llm_clients.base import BaseLLMClient

class GoogleClient(BaseLLMClient):
    """Google Gemini 客户端"""
    
    def __init__(
        self,
        model: str = "gemini-3.1-pro",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        thinking_level: Optional[str] = None,
        **kwargs
    ):
        super().__init__(model, api_key, base_url, **kwargs)
        self.thinking_level = thinking_level
    
    def get_llm(self) -> ChatGoogleGenerativeAI:
        """返回 LangChain ChatGoogleGenerativeAI 实例"""
        api_key = self.api_key or os.getenv("GOOGLE_API_KEY")
        
        llm_kwargs = {
            "model": self.model,
            "google_api_key": api_key,
            "temperature": self.temperature,
            "streaming": self.streaming,
            "max_retries": self.max_retries,
        }
        
        # Gemini 3.x 支持 thinking_level
        if self.thinking_level:
            llm_kwargs["model_kwargs"] = {
                "thinking_level": self.thinking_level
            }
        
        return ChatGoogleGenerativeAI(**llm_kwargs)
    
    def get_provider_name(self) -> str:
        return "Google"
```


### 4.6 LLM 配置系统

**`app/llm_clients/config.py`**：

```python
import os
from typing import Dict, Any, Optional

class LLMConfig:
    """LLM 配置"""
    
    # 默认配置
    DEFAULT_PROVIDER = "openai"
    DEFAULT_MODEL = "gpt-4o"
    
    # 全局默认参数
    DEFAULT_STREAMING = True
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_TEMPERATURE = 0.7
    
    # Agent 角色到模型的映射
    AGENT_MODEL_MAPPING = {
        "quant": {
            "provider": "openai",
            "model": "o1",  # o 系列推理模型
            "reasoning_effort": "high",
            "streaming": False,  # o 系列不支持流式
            "temperature": None,  # o 系列不支持 temperature
        },
        "news": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "extended_thinking": {"enabled": True, "budget_tokens": 10000},
            "streaming": True,
            "temperature": 0.7,
        },
        "social": {
            "provider": "google",
            "model": "gemini-3.1-flash",
            "thinking_level": "minimal",
            "streaming": True,
            "temperature": 0.5,
        },
        "cio": {
            "provider": "anthropic",
            "model": "claude-opus-4-6",
            "extended_thinking": {"enabled": True, "budget_tokens": 20000},
            "streaming": True,
            "temperature": 0.8,
        },
    }
    
    @classmethod
    def get_agent_config(cls, agent_type: str) -> Dict[str, Any]:
        """获取 Agent 专用配置（带默认值）"""
        config = cls.AGENT_MODEL_MAPPING.get(agent_type, {}).copy()

        # 填充默认值
        config.setdefault("provider", cls.DEFAULT_PROVIDER)
        config.setdefault("model", cls.DEFAULT_MODEL)
        config.setdefault("streaming", cls.DEFAULT_STREAMING)
        config.setdefault("max_retries", cls.DEFAULT_MAX_RETRIES)
        config.setdefault("temperature", cls.DEFAULT_TEMPERATURE)

        return config

    @classmethod
    def get_provider_config(cls, provider: str) -> Dict[str, Any]:
        """获取提供商配置"""
        provider_configs = {
            "openai": {
                "default_model": "gpt-4o",
                "supports_reasoning_effort": True,
            },
            "anthropic": {
                "default_model": "claude-opus-4-6",
                "supports_extended_thinking": True,
            },
            "google": {
                "default_model": "gemini-3.1-pro",
                "supports_thinking_level": True,
            },
        }
        return provider_configs.get(provider, {"default_model": cls.DEFAULT_MODEL})
```

**Agent 模型分配策略**：
- **Quant Agent**: OpenAI o1（高推理能力，适合解释 SHAP 归因和复杂特征）
- **News Agent**: Claude Sonnet 4.6（长上下文，适合处理大量召回文档）
- **Social Agent**: Gemini 3.1 Flash（速度优先，社交情绪分析不需要深度推理）
- **CIO Agent**: Claude Opus 4.6（最强综合能力，extended thinking 20000 tokens）

**Agent 类型映射**：

| Agent 类型字符串 | graph_multi.py 中的实际使用 | 说明 |
|----------------|---------------------------|------|
| `"quant"` | 在 Quant Agent 节点中调用 `create_llm(agent_type="quant")` | 量化技术分析 |
| `"news"` | 在 News Agent 节点中调用 `create_llm(agent_type="news")` | 新闻情绪分析 |
| `"social"` | 在 Social Agent 节点中调用 `create_llm(agent_type="social")` | 社交媒体情绪 |
| `"cio"` | 在 CIO Agent 节点中调用 `create_llm(agent_type="cio")` | 最终投资决策 |

**集成示例**：
```python
# 在 app/graph_multi.py 中
def quant_agent_node(state: AgentState):
    llm = create_llm(agent_type="quant")  # 自动使用 o1 模型
    # ... agent 逻辑
```

### 4.7 工厂函数

**`app/llm_clients/factory.py`**：

```python
from typing import Optional, Dict, Any
from app.llm_clients.base import BaseLLMClient
from app.llm_clients.config import LLMConfig
from app.llm_clients.providers.openai_client import OpenAIClient
from app.llm_clients.providers.anthropic_client import AnthropicClient
from app.llm_clients.providers.google_client import GoogleClient

def create_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    agent_type: Optional[str] = None,
    **kwargs
) -> BaseLLMClient:
    """
    LLM 客户端工厂函数
    
    Args:
        provider: LLM 提供商（"openai", "anthropic", "google"）
        model: 模型名称
        agent_type: Agent 类型（"quant", "news", "social", "cio"）
                   如果指定，会使用 Agent 专用配置
        **kwargs: 提供商特定参数
    
    Returns:
        BaseLLMClient 实例
    
    Examples:
        # 方式 1：直接指定提供商和模型
        client = create_llm_client(provider="openai", model="gpt-4o")
        
        # 方式 2：使用 Agent 预设配置
        client = create_llm_client(agent_type="quant")
        
        # 方式 3：覆盖 Agent 配置
        client = create_llm_client(
            agent_type="cio",
            extended_thinking={"enabled": True, "budget_tokens": 30000}
        )
    """
    # 如果指定了 agent_type，使用预设配置
    if agent_type:
        agent_config = LLMConfig.get_agent_config(agent_type)
        provider = provider or agent_config["provider"]
        model = model or agent_config["model"]
        # 合并 Agent 配置和用户参数
        for key, value in agent_config.items():
            if key not in ("provider", "model") and key not in kwargs:
                kwargs[key] = value
    
    # 使用默认值
    provider = provider or LLMConfig.DEFAULT_PROVIDER
    provider_config = LLMConfig.get_provider_config(provider)
    model = model or provider_config.get("default_model")
    
    # 路由到具体提供商
    if provider == "openai":
        return OpenAIClient(model=model, **kwargs)
    elif provider == "anthropic":
        return AnthropicClient(model=model, **kwargs)
    elif provider == "google":
        return GoogleClient(model=model, **kwargs)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

def create_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    agent_type: Optional[str] = None,
    **kwargs
):
    """
    便捷函数：直接返回 LangChain LLM 实例
    
    Returns:
        BaseChatModel: 可直接用于 LangGraph 的 LLM
    """
    client = create_llm_client(provider, model, agent_type, **kwargs)
    return client.get_llm()
```

### 4.8 使用示例

**基础使用**：
```python
from app.llm_clients.factory import create_llm

# 自动处理 o 系列特殊性
quant_llm = create_llm(agent_type="quant")
# 内部自动：streaming=False, temperature 被移除

# 流式输出（其他 Agent）
news_llm = create_llm(agent_type="news")
# 内部自动：streaming=True, max_retries=3
```

**结构化输出**：
```python
from pydantic import BaseModel
from app.llm_clients.factory import create_llm_client

class QuantReport(BaseModel):
    symbol: str
    recommendation: str
    confidence: float

# 创建客户端
client = create_llm_client(agent_type="quant")

# 获取结构化输出 LLM
structured_llm = client.get_structured_llm(QuantReport)

# 调用
result = structured_llm.invoke("Analyze AAPL")
# result 是 QuantReport 实例，字段保证存在
```

**在 graph_multi.py 中集成**：
```python
from app.llm_clients.factory import create_llm

# 为不同 Agent 分配不同模型
quant_llm = create_llm(agent_type="quant")  # o1 with high reasoning
news_llm = create_llm(agent_type="news")    # Claude Sonnet
cio_llm = create_llm(agent_type="cio")      # Claude Opus with extended thinking

# 在 LangGraph 中使用
def quant_agent_node(state: AgentState):
    response = quant_llm.invoke([...])
    return {"quant_report": response.content}
```


## 5. BM25 记忆系统设计

### 5.1 目录结构

```
app/memory/
├── __init__.py
├── base.py              # 记忆系统抽象基类
├── bm25_memory.py       # BM25 离线记忆
├── hybrid_memory.py     # BM25 + ChromaDB 混合检索
└── utils.py
```

### 5.2 抽象基类

**`app/memory/base.py`**：

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel

class MemoryEntry(BaseModel):
    """记忆条目"""
    situation: str          # 情境描述
    recommendation: str     # 决策建议
    metadata: Dict[str, Any] = {}  # 元数据（时间、资产、结果等）

class MemorySearchResult(BaseModel):
    """检索结果"""
    situation: str
    recommendation: str
    score: float           # 相似度分数
    metadata: Dict[str, Any] = {}

class BaseMemory(ABC):
    """
    记忆系统抽象基类

    注意：
    - BM25Memory 使用同步方法（无需 I/O）
    - HybridMemory 需要异步方法（ChromaDB 调用）
    - 子类可以选择实现同步或异步版本
    """

    @abstractmethod
    def add(self, entries: List[MemoryEntry]):
        """添加记忆（同步）"""
        pass

    @abstractmethod
    def search(self, query: str, top_k: int = 3) -> List[MemorySearchResult]:
        """检索相关记忆（同步）"""
        pass

    @abstractmethod
    def clear(self):
        """清空记忆"""
        pass
```

### 5.3 BM25 记忆实现

**`app/memory/bm25_memory.py`**：

```python
import re
from typing import List
from rank_bm25 import BM25Okapi
from app.memory.base import BaseMemory, MemoryEntry, MemorySearchResult

class BM25Memory(BaseMemory):
    """
    基于 BM25 的离线记忆系统
    
    优势：
    - 无需 API 调用，完全离线
    - 无 token 限制
    - 精确匹配关键词（如股票代码、技术指标名称）
    
    适用场景：
    - 存储历史交易决策
    - 存储 Agent 反思记录
    - 快速检索特定资产的历史分析
    """
    
    def __init__(self, name: str):
        self.name = name
        self.entries: List[MemoryEntry] = []
        self.bm25: BM25Okapi = None
    
    def _tokenize(self, text: str) -> List[str]:
        """分词（支持中英文）"""
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens
    
    def _rebuild_index(self):
        """重建 BM25 索引"""
        if self.entries:
            tokenized_docs = [
                self._tokenize(entry.situation) 
                for entry in self.entries
            ]
            self.bm25 = BM25Okapi(tokenized_docs)
        else:
            self.bm25 = None
    
    def add(self, entries: List[MemoryEntry]):
        """添加记忆并重建索引"""
        self.entries.extend(entries)
        self._rebuild_index()
    
    def search(self, query: str, top_k: int = 3) -> List[MemorySearchResult]:
        """BM25 检索"""
        if not self.entries or self.bm25 is None:
            return []
        
        # 分词查询
        query_tokens = self._tokenize(query)
        
        # 计算 BM25 分数
        scores = self.bm25.get_scores(query_tokens)
        
        # 获取 top-k
        top_indices = sorted(
            range(len(scores)), 
            key=lambda i: scores[i], 
            reverse=True
        )[:top_k]
        
        # 构建结果
        results = []
        for idx in top_indices:
            if scores[idx] > 0:  # 过滤零分结果
                entry = self.entries[idx]
                results.append(MemorySearchResult(
                    situation=entry.situation,
                    recommendation=entry.recommendation,
                    score=float(scores[idx]),
                    metadata=entry.metadata
                ))
        
        return results
    
    def clear(self):
        """清空记忆"""
        self.entries = []
        self.bm25 = None
```


### 5.4 混合记忆系统（BM25 + ChromaDB）

**`app/memory/hybrid_memory.py`**：

```python
from typing import List
from app.memory.base import BaseMemory, MemoryEntry, MemorySearchResult
from app.memory.bm25_memory import BM25Memory
from app.rag.build_event_memory import get_chroma_client

class HybridMemory(BaseMemory):
    """
    BM25 + ChromaDB 混合检索

    策略：
    1. BM25 检索：精确匹配关键词（股票代码、指标名称）
    2. ChromaDB 检索：语义相似度（模糊概念、情绪描述）
    3. 结果融合：RRF (Reciprocal Rank Fusion)

    适用场景：
    - 需要同时匹配精确关键词和语义相似度
    - 例如："AAPL 的 MACD 金叉" 既要匹配 "AAPL" 和 "MACD"，
      也要理解 "金叉" 的语义

    注意：
    - 实现了同步 search() 方法（继承自 BaseMemory）
    - ChromaDB 查询在同步上下文中执行
    - 如需异步，可添加 search_async() 方法
    """

    def __init__(self, name: str, chroma_collection_name: str):
        self.name = name
        self.bm25_memory = BM25Memory(f"{name}_bm25")
        self.chroma_client = get_chroma_client()
        self.chroma_collection = self.chroma_client.get_or_create_collection(
            chroma_collection_name
        )
    
    def add(self, entries: List[MemoryEntry]):
        """同时添加到 BM25 和 ChromaDB"""
        # 添加到 BM25
        self.bm25_memory.add(entries)
        
        # 添加到 ChromaDB
        for i, entry in enumerate(entries):
            self.chroma_collection.add(
                documents=[entry.situation],
                metadatas=[{
                    "recommendation": entry.recommendation,
                    **entry.metadata
                }],
                ids=[f"{self.name}_{len(self.bm25_memory.entries) - len(entries) + i}"]
            )
    
    def search(self, query: str, top_k: int = 3) -> List[MemorySearchResult]:
        """混合检索（BM25 + ChromaDB）"""
        # 1. BM25 检索
        bm25_results = self.bm25_memory.search(query, top_k=top_k * 2)
        
        # 2. ChromaDB 检索
        chroma_results = self.chroma_collection.query(
            query_texts=[query],
            n_results=top_k * 2
        )
        
        # 3. RRF 融合
        fused_results = self._reciprocal_rank_fusion(
            bm25_results,
            chroma_results,
            top_k=top_k
        )
        
        return fused_results
    
    def _reciprocal_rank_fusion(
        self,
        bm25_results: List[MemorySearchResult],
        chroma_results: dict,
        top_k: int,
        k: int = 60
    ) -> List[MemorySearchResult]:
        """
        RRF 融合算法
        
        RRF(d) = Σ 1 / (k + rank(d))
        
        Args:
            k: RRF 常数（通常为 60）
        """
        scores = {}
        
        # BM25 结果
        for rank, result in enumerate(bm25_results, start=1):
            key = result.situation
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
        
        # ChromaDB 结果
        for rank, (doc, metadata) in enumerate(
            zip(chroma_results['documents'][0], chroma_results['metadatas'][0]),
            start=1
        ):
            key = doc
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
        
        # 排序并返回 top-k
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)[:top_k]

        # 构建结果映射（从两个来源）
        result_map = {r.situation: r for r in bm25_results}
        chroma_map = {
            doc: metadata
            for doc, metadata in zip(
                chroma_results['documents'][0],
                chroma_results['metadatas'][0]
            )
        }

        # 构建最终结果
        results = []
        for key in sorted_keys:
            if key in result_map:
                # 从 BM25 结果中获取
                result = result_map[key]
                results.append(MemorySearchResult(
                    situation=result.situation,
                    recommendation=result.recommendation,
                    score=scores[key],
                    metadata=result.metadata
                ))
            elif key in chroma_map:
                # 从 ChromaDB 结果中获取
                metadata = chroma_map[key]
                results.append(MemorySearchResult(
                    situation=key,
                    recommendation=metadata.get('recommendation', ''),
                    score=scores[key],
                    metadata=metadata
                ))

        return results
    
    def clear(self):
        """清空两个记忆系统"""
        self.bm25_memory.clear()
        self.chroma_collection.delete()
```

### 5.5 与 Agent 集成

**在 CIO Agent 中使用记忆系统**：

```python
from app.memory.hybrid_memory import HybridMemory
from app.memory.base import MemoryEntry
from datetime import datetime

# 初始化混合记忆（BM25 + ChromaDB）
cio_memory = HybridMemory(
    name="cio_decisions",
    chroma_collection_name="cio_decision_memory"
)

# 添加历史决策
cio_memory.add([
    MemoryEntry(
        situation="AAPL 在 2024-01-15 的分析：技术面 MACD 金叉，新闻面苹果发布 Vision Pro",
        recommendation="强烈买入，目标价 $200，止损 $180",
        metadata={
            "symbol": "AAPL",
            "date": "2024-01-15",
            "actual_outcome": "涨幅 +15%",
            "decision_quality": "excellent"
        }
    ),
])

# 在 Agent 中使用
def cio_agent_with_memory(state: AgentState):
    query = state["query"]
    
    # 检索相关历史决策
    relevant_memories = cio_memory.search(query, top_k=3)
    
    # 构建 prompt（包含历史经验）
    memory_context = "\n".join([
        f"历史案例 {i+1}:\n情境: {m.situation}\n决策: {m.recommendation}\n结果: {m.metadata.get('actual_outcome', 'N/A')}"
        for i, m in enumerate(relevant_memories)
    ])
    
    prompt = f"""
    你是 CIO，需要分析以下资产：
    {query}
    
    参考以下历史决策经验：
    {memory_context}
    
    当前分析报告：
    - 量化报告：{state['quant_report']}
    - 新闻报告：{state['news_report']}
    - 社交报告：{state['social_report']}
    
    请给出你的投资建议。
    """
    
    # 调用 LLM
    llm = create_llm(agent_type="cio")
    response = llm.invoke(prompt)
    
    # 保存本次决策到记忆
    cio_memory.add([
        MemoryEntry(
            situation=f"{query} 的分析：{state['quant_report'][:100]}...",
            recommendation=response.content,
            metadata={
                "date": datetime.now().isoformat(),
                "run_id": state.get("run_id")
            }
        )
    ])
    
    return {"final_decision": response.content}
```

### 5.6 记忆系统对比

| 特性 | BM25Memory | ChromaDB RAG | HybridMemory |
|------|-----------|--------------|--------------|
| **检索方式** | 关键词匹配 | 语义相似度 | 混合（RRF 融合） |
| **API 调用** | 无 | 需要（embedding） | 需要（embedding） |
| **Token 限制** | 无 | 有 | 有 |
| **精确匹配** | ✓ 优秀 | ✗ 较弱 | ✓ 优秀 |
| **语义理解** | ✗ 不支持 | ✓ 优秀 | ✓ 优秀 |
| **适用场景** | 股票代码、指标名称 | 模糊概念、情绪描述 | 综合查询 |

**推荐使用策略**：
- **Quant Agent**: BM25Memory（精确匹配技术指标名称）
- **News Agent**: ChromaDB RAG（语义理解新闻主题）
- **CIO Agent**: HybridMemory（综合历史决策经验）


## 6. 实施计划

### 6.1 阶段划分

**阶段 1：数据提供商抽象层（第 1 周）**

**任务清单**：
1. 创建目录结构 `app/dataflows/`
2. 实现 Pydantic 数据模型（`models.py`）
3. 实现异步抽象基类（`base.py`）
4. 实现 Redis 缓存层（`cache.py`）
5. 实现 MCP 适配器（`providers/mcp_provider.py`）
6. 实现 yfinance 适配器（`providers/yfinance_provider.py`）
7. 实现路由器（`interface.py`）
8. 编写单元测试

**验收标准**：
- MCP 服务器挂掉时自动降级到 yfinance
- 历史数据缓存命中率 > 80%
- 所有单元测试通过

---

**阶段 2：LLM 提供商工厂模式（第 2 周前半）**

**任务清单**：
1. 创建目录结构 `app/llm_clients/`
2. 实现抽象基类（`base.py`）
3. 实现 OpenAI 客户端（`providers/openai_client.py`）
4. 实现 Anthropic 客户端（`providers/anthropic_client.py`）
5. 实现 Google 客户端（`providers/google_client.py`）
6. 实现配置系统（`config.py`）
7. 实现工厂函数（`factory.py`）
8. 重构 `app/llm_config.py`
9. 更新 `app/graph_multi.py` 使用新工厂
10. 编写单元测试

**验收标准**：
- 所有 Agent 使用专用模型配置
- o 系列模型参数自动过滤
- 结构化输出正常工作
- 所有单元测试通过

---

**阶段 3：BM25 记忆系统（第 2 周后半）**

**任务清单**：
1. 创建目录结构 `app/memory/`
2. 实现抽象基类（`base.py`）
3. 实现 BM25 记忆（`bm25_memory.py`）
4. 实现混合记忆（`hybrid_memory.py`）
5. 集成到 CIO Agent
6. 编写单元测试

**验收标准**：
- BM25 精确匹配股票代码和指标名称
- 混合检索 RRF 融合正常工作
- CIO Agent 能够引用历史决策
- 所有单元测试通过

### 6.2 迁移策略

**向后兼容迁移**：

1. **数据层迁移**：
   ```python
   # 旧代码继续工作
   from app.mcp_client.finance_client import FinanceMCPClient
   client = FinanceMCPClient("http://localhost:8000")
   
   # 新代码逐步迁移
   from app.dataflows.interface import DataFlowRouter
   router = DataFlowRouter()
   ```

2. **LLM 层迁移**：
   ```python
   # 旧代码继续工作
   from app.llm_config import create_llm
   llm = create_llm()
   
   # 新代码使用 Agent 专用配置
   from app.llm_clients.factory import create_llm
   llm = create_llm(agent_type="quant")
   ```

3. **逐个 Agent 迁移**：
   - 第 1 周：迁移 Quant Agent
   - 第 2 周：迁移 News Agent 和 Social Agent
   - 第 3 周：迁移 CIO Agent（集成记忆系统）

### 6.3 测试策略

**单元测试**：

```python
# tests/test_dataflows.py
import pytest
from app.dataflows.interface import DataFlowRouter
from app.dataflows.providers.mcp_provider import MCPDataProvider
from datetime import datetime

@pytest.mark.asyncio
async def test_mcp_fallback_to_yfinance():
    """测试 MCP 失败时自动降级到 yfinance"""
    router = DataFlowRouter(config={
        "data_vendors": {"stock_data": "mcp"},
        "mcp_servers": {"market_data": "http://invalid:9999"},  # 无效地址
    })
    
    # 应该自动降级到 yfinance
    result = await router.get_stock_data(
        "AAPL",
        datetime(2024, 1, 1),
        datetime(2024, 12, 31)
    )
    
    assert len(result) > 0
    assert result[0].symbol == "AAPL"

@pytest.mark.asyncio
async def test_cache_hit():
    """测试缓存命中"""
    router = DataFlowRouter(enable_cache=True)
    
    # 第一次调用（缓存未命中）
    result1 = await router.get_stock_data("AAPL", ...)
    
    # 第二次调用（缓存命中）
    result2 = await router.get_stock_data("AAPL", ...)
    
    assert result1 == result2
```

```python
# tests/test_llm_clients.py
import pytest
from app.llm_clients.factory import create_llm_client

def test_o_series_filters_temperature():
    """测试 o 系列模型自动过滤 temperature"""
    client = create_llm_client(
        provider="openai",
        model="o1",
        temperature=0.7
    )
    
    assert not client.supports_streaming()
    llm = client.get_llm()
    # 验证 temperature 未传递
```

```python
# tests/test_memory.py
from app.memory.bm25_memory import BM25Memory
from app.memory.base import MemoryEntry

def test_bm25_exact_match():
    """测试 BM25 精确匹配股票代码"""
    memory = BM25Memory("test")
    
    memory.add([
        MemoryEntry(
            situation="AAPL 在 2024-01-15 MACD 金叉",
            recommendation="买入"
        )
    ])
    
    results = memory.search("AAPL", top_k=1)
    
    assert len(results) == 1
    assert "AAPL" in results[0].situation
```

**集成测试**：

```bash
# 启动 MCP 服务器
bash scripts/start_mcp_servers.sh

# 运行集成测试
uv run pytest tests/integration/ -v

# 测试完整 Agent 流程
uv run python -c "from app.graph_multi import run_once; print(run_once('Analyze AAPL'))"
```


## 7. 配置示例

### 7.1 环境变量配置

**`.env` 文件**：

```bash
# LLM API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# 数据提供商 API Keys
POLYGON_API_KEY=...
ALPHA_VANTAGE_API_KEY=...

# Redis 缓存
REDIS_URL=redis://localhost:6379

# MCP 服务器地址
MCP_MARKET_DATA_URL=http://localhost:8000
MCP_NEWS_SEARCH_URL=http://localhost:8001
```

### 7.2 数据提供商配置

**`app/dataflows/config.py`**：

```python
DEFAULT_CONFIG = {
    # 数据提供商配置（类别级）
    "data_vendors": {
        "stock_data": "mcp",              # 主数据源：MCP
        "technical_indicators": "mcp",
        "news": "mcp",
        "fundamentals": "yfinance",       # 基本面用 yfinance
    },
    
    # 工具级覆盖（可选）
    "tool_vendors": {
        # 示例：特定工具使用不同提供商
        # "get_stock_data": "polygon",
    },
    
    # 备用提供商（降级策略）
    "fallback_vendor": "yfinance",
    
    # MCP 服务器地址
    "mcp_servers": {
        "market_data": os.getenv("MCP_MARKET_DATA_URL", "http://localhost:8000"),
        "news_search": os.getenv("MCP_NEWS_SEARCH_URL", "http://localhost:8001"),
    },
    
    # Redis 缓存
    "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
}
```

### 7.3 LLM 配置

**`app/llm_clients/config.py`**：

```python
AGENT_MODEL_MAPPING = {
    "quant": {
        "provider": "openai",
        "model": "o1",
        "reasoning_effort": "high",
        "streaming": False,
    },
    "news": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "extended_thinking": {"enabled": True, "budget_tokens": 10000},
        "streaming": True,
    },
    "social": {
        "provider": "google",
        "model": "gemini-3.1-flash",
        "thinking_level": "minimal",
        "streaming": True,
    },
    "cio": {
        "provider": "anthropic",
        "model": "claude-opus-4-6",
        "extended_thinking": {"enabled": True, "budget_tokens": 20000},
        "streaming": True,
    },
}
```

### 7.4 CLAUDE.md 更新

```markdown
## 架构改进（2026-03-26）

### 数据提供商抽象层
- 主数据源：MCP 服务器（localhost:8000, localhost:8001）
- 备用数据源：yfinance（MCP 失败时自动降级）
- 缓存策略：Redis（历史数据 7 天 TTL，新闻 1 小时 TTL）

### LLM 提供商配置
- Quant Agent: OpenAI o1（高推理能力）
- News Agent: Claude Sonnet 4.6（长上下文）
- Social Agent: Gemini 3.1 Flash（速度优先）
- CIO Agent: Claude Opus 4.6（最强综合能力）

### 记忆系统
- CIO Agent 使用混合记忆（BM25 + ChromaDB）
- 存储历史决策和反思记录
- 支持精确关键词匹配和语义检索

### 切换数据源
修改 `app/dataflows/config.py` 中的 `data_vendors` 配置：
```python
"data_vendors": {
    "stock_data": "polygon",  # 切换到 Polygon
}
```

### 切换 LLM 提供商
修改 `app/llm_clients/config.py` 中的 `AGENT_MODEL_MAPPING`：
```python
"quant": {
    "provider": "anthropic",
    "model": "claude-opus-4-6",
}
```
```


## 8. 风险评估与缓解

### 8.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **Redis 缓存故障** | 性能下降，但功能正常 | 低 | 缓存层可选，`enable_cache=False` 禁用 |
| **异步迁移复杂度** | 开发周期延长 | 中 | 保持同步接口兼容，逐步迁移 |
| **Pydantic V2 兼容性** | 序列化问题 | 低 | 使用 `model_dump()` 替代 `dict()` |
| **o 系列模型限制** | 功能受限 | 低 | 自动过滤不支持参数 |
| **提供商 API 变更** | 适配器失效 | 中 | 抽象层隔离变更，只需更新适配器 |

### 8.2 性能风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **Redis 缓存未命中** | 延迟增加 | 中 | 预热缓存，调整 TTL 策略 |
| **异步并发问题** | 资源竞争 | 低 | 使用连接池，限制并发数 |
| **BM25 索引重建慢** | 添加记忆延迟 | 低 | 批量添加，异步重建索引 |

### 8.3 运维风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **配置错误** | 服务不可用 | 中 | 配置验证，默认值兜底 |
| **API Key 泄露** | 安全风险 | 低 | 使用环境变量，不提交 `.env` |
| **MCP 服务器宕机** | 数据获取失败 | 中 | 自动降级到 yfinance |

## 9. 总结

### 9.1 核心价值

本设计方案通过借鉴 TradingAgents 的三个核心架构模式，为 finance-agent 项目带来以下价值：

1. **数据源灵活性**：
   - 配置级切换数据提供商，无需改代码
   - 运行时自动降级，提升系统可用性
   - Redis 缓存降低 API 调用成本

2. **LLM 提供商灵活性**：
   - 支持 OpenAI/Anthropic/Google 多提供商
   - Agent 专用模型优化（Quant 用推理模型，Social 用快速模型）
   - 自动处理提供商特定限制（o 系列参数过滤）

3. **决策质量提升**：
   - BM25 记忆系统存储历史决策
   - 混合检索（BM25 + ChromaDB）综合精确匹配和语义理解
   - CIO Agent 能够引用历史经验

### 9.2 关键设计亮点

1. **Pydantic 数据契约**：所有数据提供商返回标准化模型，Agent 层完全解耦
2. **异步高并发**：全异步接口，支持并发获取多只股票数据
3. **智能缓存策略**：历史数据 7 天 TTL，新闻 1 小时 TTL
4. **运行时降级**：MCP 超时自动切换 yfinance，对用户透明
5. **结构化输出统一接口**：`get_structured_llm(schema)` 处理提供商差异
6. **RRF 混合检索**：BM25 精确匹配 + ChromaDB 语义理解

### 9.3 实施建议

1. **优先级排序**：
   - P0：数据提供商抽象层（解决 yfinance 超时问题）
   - P1：LLM 提供商工厂（优化 Agent 模型分配）
   - P2：BM25 记忆系统（提升决策质量）

2. **渐进迁移**：
   - 保持向后兼容，旧代码继续工作
   - 逐个 Agent 迁移到新抽象层
   - 充分测试后再全面切换

3. **监控指标**：
   - 缓存命中率（目标 > 80%）
   - 降级触发次数（监控 MCP 稳定性）
   - Agent 响应时间（异步优化效果）
   - 记忆检索准确率（BM25 vs ChromaDB）

### 9.4 后续扩展方向

1. **数据提供商扩展**：
   - 添加 Polygon 适配器
   - 添加 Alpha Vantage 适配器
   - 支持自定义数据源

2. **LLM 提供商扩展**：
   - 添加 xAI Grok 支持
   - 添加本地模型（Ollama）支持
   - 支持模型路由（根据任务复杂度自动选择模型）

3. **记忆系统增强**：
   - 定期回顾历史决策的实际结果
   - 基于结果质量调整记忆权重
   - 支持记忆遗忘（淘汰低质量决策）

---

**设计完成日期**：2026-03-26  
**预计实施周期**：2 周  
**风险等级**：低  
**预期收益**：高

