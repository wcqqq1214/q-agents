# Redis 集成实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Finance Agent 项目集成 Redis，实现分布式缓存、API 限流和异步任务队列，提升系统性能和可靠性

**Architecture:** Redis 优先 + 内存容灾的混合缓存策略，本地熔断器保证降级可用性，基于 Lua 脚本的原子限流器，ARQ 异步任务队列与 FastAPI 无缝集成

**Tech Stack:** redis[asyncio], arq, pyarrow (Parquet), msgpack, APScheduler, FastAPI

---

## 文件结构规划

### 新增文件
```
app/services/redis_client.py       # Redis 连接客户端（连接池、熔断器）
app/services/rate_limiter.py       # 限流装饰器和 Lua 脚本
app/config/rate_limits.py          # 限流配置常量
app/tasks/worker_settings.py       # ARQ Worker 配置
docker-compose.yml                 # Docker Compose 配置
tests/services/test_redis_client.py
tests/services/test_hot_cache_redis.py
tests/services/test_rate_limiter.py
```

### 修改文件
```
pyproject.toml                     # 添加 Redis 相关依赖
.env.example                       # 添加 Redis 配置项
app/config_manager.py              # 添加 Redis 配置管理方法
app/services/hot_cache.py          # 重构为 Redis 优先缓存
app/okx/trading_client.py          # 添加限流装饰器
app/services/binance_client.py     # 添加限流装饰器
app/polygon/client.py              # 添加限流装饰器
app/tasks/update_ohlc.py           # 适配 ARQ 任务格式
```

---

## 阶段 1：基础设施搭建

### Task 1: 添加 Redis 依赖

**Files:**
- Modify: `pyproject.toml:7-38`
- Modify: `.env.example`

- [ ] **Step 1: 更新 pyproject.toml 添加依赖**

在 `dependencies` 列表末尾添加：
```toml
    "redis[asyncio]>=5.0.0",
    "arq>=0.26.0",
    "hiredis>=2.3.0",
    "msgpack>=1.0.0",
    "pyarrow>=15.0.0",
```

- [ ] **Step 2: 安装依赖**

Run: `uv sync`
Expected: 成功安装所有新依赖

- [ ] **Step 3: 更新 .env.example 添加 Redis 配置**

在文件末尾添加：
```bash
# ============================================
# Redis 配置
# ============================================
REDIS_URL=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=100
REDIS_SOCKET_TIMEOUT=2
REDIS_SOCKET_CONNECT_TIMEOUT=2
REDIS_POOL_TIMEOUT=1
REDIS_HEALTH_CHECK_INTERVAL=30
REDIS_ENABLED=true

# ============================================
# 限流器配置
# ============================================
INSTANCE_COUNT=4

# ============================================
# ARQ 任务队列配置
# ============================================
ARQ_WORKER_COUNT=2
ARQ_JOB_TIMEOUT=600
ARQ_KEEP_RESULT=3600
```

- [ ] **Step 4: 复制到 .env 文件**

Run: `cp .env.example .env` (如果 .env 不存在)
Expected: 配置文件就绪

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example
git commit -m "chore: add Redis and ARQ dependencies"
```

### Task 2: 创建 Docker Compose 配置

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: 创建 docker-compose.yml**

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: finance-agent-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    restart: unless-stopped

volumes:
  redis_data:
    driver: local
```

- [ ] **Step 2: 启动 Redis 容器**

Run: `docker-compose up -d redis`
Expected: Redis 容器成功启动

- [ ] **Step 3: 验证 Redis 可用**

Run: `docker-compose logs redis | head -20`
Expected: 看到 "Ready to accept connections"

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add Docker Compose configuration for Redis"
```

### Task 3: 更新 ConfigManager

**Files:**
- Modify: `app/config_manager.py:179-183`

- [ ] **Step 1: 添加 Redis 配置方法**

在 `ConfigManager` 类末尾添加：
```python
    def get_redis_settings(self) -> Dict[str, Any]:
        """获取 Redis 配置"""
        return {
            "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            "redis_enabled": os.getenv("REDIS_ENABLED", "true").lower() == "true",
            "max_connections": int(os.getenv("REDIS_MAX_CONNECTIONS", "100")),
            "socket_timeout": int(os.getenv("REDIS_SOCKET_TIMEOUT", "2")),
            "socket_connect_timeout": int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "2")),
            "pool_timeout": int(os.getenv("REDIS_POOL_TIMEOUT", "1")),
        }

    def update_redis_settings(
        self,
        redis_url: Optional[str] = None,
        redis_enabled: Optional[bool] = None
    ) -> Dict[str, Any]:
        """更新 Redis 配置"""
        updates = {}
        if redis_url:
            updates["REDIS_URL"] = redis_url
        if redis_enabled is not None:
            updates["REDIS_ENABLED"] = "true" if redis_enabled else "false"

        if updates:
            self._update_env_file(updates)

        return self.get_redis_settings()
```

- [ ] **Step 2: 添加导入**

在文件顶部添加：
```python
from typing import Dict, Optional, Any
```

- [ ] **Step 3: Commit**

```bash
git add app/config_manager.py
git commit -m "feat: add Redis configuration management methods"
```

## 阶段 2：Redis 客户端和熔断器

### Task 4: 创建 Redis 客户端（含熔断器）

**Files:**
- Create: `app/services/redis_client.py`
- Create: `tests/services/test_redis_client.py`

- [ ] **Step 1: 写测试 - Redis 连接和熔断器**

```python
# tests/services/test_redis_client.py
import pytest
from app.services.redis_client import get_redis_client, CircuitState, CircuitBreaker

@pytest.mark.asyncio
async def test_redis_client_connection():
    """测试 Redis 客户端连接"""
    client = await get_redis_client()
    assert client is not None
    await client.ping()

def test_circuit_breaker_state_transitions():
    """测试熔断器状态转换"""
    cb = CircuitBreaker()

    # 初始状态：CLOSED
    assert cb.state == CircuitState.CLOSED
    assert cb.can_attempt() is True

    # 累积 5 次失败 → OPEN
    for _ in range(5):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_attempt() is False

    # 等待恢复时间后 → HALF_OPEN
    cb.next_retry_time = None  # 模拟时间已过
    assert cb.can_attempt() is True
    assert cb.state == CircuitState.HALF_OPEN

    # HALF_OPEN 状态下失败 → 立即 OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # HALF_OPEN 状态下成功 → CLOSED
    cb.state = CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/services/test_redis_client.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 实现 CircuitBreaker 类**

- [ ] **Step 3: 实现 CircuitBreaker 类**

```python
# app/services/redis_client.py
"""Redis 客户端（含熔断器和连接池管理）"""
import logging
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """本地熔断器（每个实例独立维护）"""
    def __init__(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.next_retry_time: Optional[datetime] = None

    def record_failure(self):
        """记录失败"""
        self.last_failure_time = datetime.now()

        # 半开状态下失败，立即重新熔断
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.next_retry_time = datetime.now() + timedelta(seconds=30)
            logger.warning("Circuit breaker re-OPENED: Probe failed")
            return

        # 正常累加错误
        self.failure_count += 1
        if self.failure_count >= 5:
            self.state = CircuitState.OPEN
            self.next_retry_time = datetime.now() + timedelta(seconds=30)
            logger.warning("Circuit breaker OPEN: Redis unavailable")

    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        logger.info("Circuit breaker CLOSED: Redis recovered")

    def can_attempt(self) -> bool:
        """是否允许尝试请求"""
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if self.next_retry_time and datetime.now() >= self.next_retry_time:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker HALF_OPEN: Probing Redis")
                return True
            return False
        else:  # HALF_OPEN
            return True

# 全局熔断器实例
_circuit_breaker = CircuitBreaker()

def get_circuit_breaker() -> CircuitBreaker:
    """获取熔断器实例"""
    return _circuit_breaker
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/services/test_redis_client.py::test_circuit_breaker_state_transitions -v`
Expected: PASS

- [ ] **Step 5: 实现 Redis 客户端连接池**

在 `app/services/redis_client.py` 添加：
```python
import os
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError, ConnectionError, TimeoutError

# 全局 Redis 客户端
_redis_client: Optional[Redis] = None

async def get_redis_client() -> Redis:
    """获取 Redis 客户端（单例）"""
    global _redis_client

    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", "100"))
        socket_timeout = int(os.getenv("REDIS_SOCKET_TIMEOUT", "2"))
        socket_connect_timeout = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "2"))

        pool = ConnectionPool.from_url(
            redis_url,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            decode_responses=False,  # 二进制模式
        )

        _redis_client = Redis(connection_pool=pool)
        logger.info(f"Redis client initialized: {redis_url}")

    return _redis_client
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/services/test_redis_client.py::test_redis_client_connection -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/redis_client.py tests/services/test_redis_client.py
git commit -m "feat: add Redis client with circuit breaker"
```

## 阶段 3：缓存层重构

### Task 5: 重构 hot_cache 为 Redis 优先缓存

**Files:**
- Modify: `app/services/hot_cache.py`
- Create: `tests/services/test_hot_cache_redis.py`

- [ ] **Step 1: 写测试 - Redis 缓存读写**

```python
# tests/services/test_hot_cache_redis.py
import pytest
import pandas as pd
from app.services.hot_cache import get_hot_cache, set_hot_cache

@pytest.mark.asyncio
async def test_redis_cache_set_and_get():
    """测试 Redis 缓存读写"""
    symbol = "BTCUSDT"
    interval = "1m"
    test_data = pd.DataFrame({
        'timestamp': [1234567890000],
        'date': ['2024-01-01T00:00:00Z'],
        'open': [50000.0],
        'high': [51000.0],
        'low': [49000.0],
        'close': [50500.0],
        'volume': [100.0]
    })

    # 写入缓存
    await set_hot_cache(symbol, interval, test_data, ttl=60)

    # 读取缓存
    result = await get_hot_cache(symbol, interval)

    assert not result.empty
    assert len(result) == 1
    assert result['close'].iloc[0] == 50500.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/services/test_hot_cache_redis.py::test_redis_cache_set_and_get -v`
Expected: FAIL (函数签名不匹配)

- [ ] **Step 3: 重构 hot_cache.py - 添加 Redis 支持**

完全重写 `app/services/hot_cache.py`：
```python
"""
Hot cache infrastructure with Redis-first + memory fallback strategy.
"""
import logging
import io
from typing import Dict, Optional
import pandas as pd
from datetime import datetime

from app.services.redis_client import get_redis_client, get_circuit_breaker
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# 内存缓存（降级使用）
HOT_CACHE: Dict[str, Dict[str, pd.DataFrame]] = {
    "BTCUSDT": {},
    "ETHUSDT": {},
}

CACHE_COLUMNS = ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']

def _generate_cache_key(symbol: str, interval: str) -> str:
    """生成 Redis 缓存 key"""
    return f"cache:kline:{symbol}:{interval}:latest"

async def get_hot_cache(symbol: str, interval: str) -> pd.DataFrame:
    """
    获取缓存数据（Redis 优先，降级到内存）

    Args:
        symbol: 交易对符号
        interval: 时间间隔

    Returns:
        DataFrame 或空 DataFrame
    """
    circuit_breaker = get_circuit_breaker()

    # 尝试从 Redis 读取
    if circuit_breaker.can_attempt():
        try:
            redis = await get_redis_client()
            key = _generate_cache_key(symbol, interval)
            data = await redis.get(key)

            if data:
                # 使用 Parquet 反序列化
                df = pd.read_parquet(io.BytesIO(data))
                circuit_breaker.record_success()
                logger.debug(f"Cache HIT (Redis): {symbol} {interval}")
                return df
            else:
                logger.debug(f"Cache MISS (Redis): {symbol} {interval}")
                return pd.DataFrame(columns=CACHE_COLUMNS)

        except (RedisError, Exception) as e:
            logger.warning(f"Redis read failed: {e}, falling back to memory")
            circuit_breaker.record_failure()

    # 降级到内存缓存
    logger.debug(f"Using memory cache (degraded mode): {symbol} {interval}")
    if symbol not in HOT_CACHE:
        return pd.DataFrame(columns=CACHE_COLUMNS)

    if interval not in HOT_CACHE[symbol]:
        return pd.DataFrame(columns=CACHE_COLUMNS)

    return HOT_CACHE[symbol][interval].copy()

async def set_hot_cache(
    symbol: str,
    interval: str,
    data: pd.DataFrame,
    ttl: int = 3600
) -> None:
    """
    写入缓存（Redis 优先，降级到内存）

    Args:
        symbol: 交易对符号
        interval: 时间间隔
        data: K 线数据
        ttl: 过期时间（秒）
    """
    circuit_breaker = get_circuit_breaker()

    # 尝试写入 Redis
    if circuit_breaker.can_attempt():
        try:
            redis = await get_redis_client()
            key = _generate_cache_key(symbol, interval)

            # 使用 Parquet 序列化
            buffer = io.BytesIO()
            data.to_parquet(buffer, engine='pyarrow', compression='snappy')
            await redis.set(key, buffer.getvalue(), ex=ttl)

            circuit_breaker.record_success()
            logger.debug(f"Cache SET (Redis): {symbol} {interval}, TTL={ttl}s")
            return

        except (RedisError, Exception) as e:
            logger.warning(f"Redis write failed: {e}, falling back to memory")
            circuit_breaker.record_failure()

    # 降级到内存缓存
    logger.debug(f"Cache SET (memory, degraded mode): {symbol} {interval}")
    if symbol not in HOT_CACHE:
        HOT_CACHE[symbol] = {}

    HOT_CACHE[symbol][interval] = data.copy()

# 保留旧的同步接口（向后兼容）
def append_to_hot_cache(symbol: str, interval: str, new_data: list) -> None:
    """向后兼容的同步接口（已废弃，建议使用 set_hot_cache）"""
    logger.warning("append_to_hot_cache is deprecated, use set_hot_cache instead")
    if symbol not in HOT_CACHE:
        HOT_CACHE[symbol] = {}
    if interval not in HOT_CACHE[symbol]:
        HOT_CACHE[symbol][interval] = pd.DataFrame(columns=CACHE_COLUMNS)

    new_df = pd.DataFrame(new_data) if new_data else pd.DataFrame(columns=CACHE_COLUMNS)
    combined = pd.concat([HOT_CACHE[symbol][interval], new_df], ignore_index=True)

    if 'timestamp' in combined.columns and len(combined) > 0:
        combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
        combined = combined.sort_values('timestamp').reset_index(drop=True)

    if len(combined) > 2880:
        combined = combined.tail(2880).reset_index(drop=True)

    HOT_CACHE[symbol][interval] = combined
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/services/test_hot_cache_redis.py::test_redis_cache_set_and_get -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/hot_cache.py tests/services/test_hot_cache_redis.py
git commit -m "refactor: migrate hot_cache to Redis-first with memory fallback"
```

## 阶段 4：API 限流器

### Task 6: 创建限流配置和 Lua 脚本

**Files:**
- Create: `app/config/rate_limits.py`
- Create: `app/services/rate_limiter.py`
- Create: `tests/services/test_rate_limiter.py`

- [ ] **Step 1: 创建限流配置**

```python
# app/config/rate_limits.py
"""限流配置常量"""
import os

# 每个交易所的限流配置
RATE_LIMITS = {
    "binance": {"max_requests": 1200, "window": 60},  # 1200 请求/60秒
    "okx": {"max_requests": 20, "window": 1},         # 20 请求/秒
    "polygon": {"max_requests": 5, "window": 60},     # 5 请求/60秒
}

# 实例数量（用于降级时的配额分配）
INSTANCE_COUNT = int(os.getenv("INSTANCE_COUNT", "4"))

# 降级时的本地限流配置（全局配额 / 实例数）
FALLBACK_RATE_LIMITS = {
    exchange: {
        "max_requests": config["max_requests"] // INSTANCE_COUNT,
        "window": config["window"]
    }
    for exchange, config in RATE_LIMITS.items()
}
```

- [ ] **Step 2: 写测试 - 限流器基本功能和拒绝**

```python
# tests/services/test_rate_limiter.py
import pytest
import asyncio
from app.services.rate_limiter import check_rate_limit

@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit():
    """测试限流器在配额内允许请求"""
    exchange = "binance"
    identifier = "test_user_allow"

    # 第一次请求应该被允许
    allowed = await check_rate_limit(exchange, identifier)
    assert allowed is True

@pytest.mark.asyncio
async def test_rate_limiter_rejects_over_limit():
    """测试限流器超过配额时拒绝请求"""
    exchange = "polygon"  # 5 请求/60秒
    identifier = "test_user_reject"

    # 发送 5 次请求（配额内）
    for i in range(5):
        allowed = await check_rate_limit(exchange, identifier)
        assert allowed is True, f"Request {i+1} should be allowed"

    # 第 6 次请求应该被拒绝
    allowed = await check_rate_limit(exchange, identifier)
    assert allowed is False, "Request 6 should be rejected"

@pytest.mark.asyncio
async def test_rate_limiter_concurrent_requests():
    """测试限流器并发请求的原子性"""
    exchange = "okx"  # 20 请求/秒
    identifier = "test_concurrent"

    # 并发发送 25 次请求
    tasks = [check_rate_limit(exchange, identifier) for _ in range(25)]
    results = await asyncio.gather(*tasks)

    # 应该有 20 个 True，5 个 False
    allowed_count = sum(results)
    assert allowed_count == 20, f"Expected 20 allowed, got {allowed_count}"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest tests/services/test_rate_limiter.py::test_rate_limiter_allows_within_limit -v`
Expected: FAIL (模块不存在)

- [ ] **Step 4: 实现限流器（含 Lua 脚本）**

```python
# app/services/rate_limiter.py
"""API 限流器（Redis + 本地降级）"""
import logging
import uuid
import time
import functools
import inspect
from collections import deque
from typing import Callable, Optional
from redis.exceptions import RedisError

from app.services.redis_client import get_redis_client, get_circuit_breaker
from app.config.rate_limits import RATE_LIMITS, FALLBACK_RATE_LIMITS

logger = logging.getLogger(__name__)

# Lua 脚本（原子性保证）
RATE_LIMIT_LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local request_id = ARGV[4]

-- 删除窗口外的旧记录
local window_start = now - window * 1000
redis.call('ZREMRANGEBYSCORE', key, 0, window_start)

-- 统计当前窗口内的请求数
local count = redis.call('ZCARD', key)

if count < max_requests then
    -- 允许请求，添加新记录
    redis.call('ZADD', key, now, request_id)
    redis.call('PEXPIRE', key, window * 1000)
    return 1
else
    return 0
end
"""

# 本地限流器（降级使用）
class LocalRateLimiter:
    """本地滑动窗口限流器"""
    def __init__(self, max_requests: int, window: int):
        self.max_requests = max_requests
        self.window = window
        self.requests = deque()

    def is_allowed(self) -> bool:
        now = time.time()
        # 移除窗口外的请求
        while self.requests and self.requests[0] < now - self.window:
            self.requests.popleft()

        # 检查是否超限
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False

# 全局本地限流器实例
_local_limiters = {}

def _get_local_limiter(exchange: str) -> LocalRateLimiter:
    """获取本地限流器实例"""
    if exchange not in _local_limiters:
        config = FALLBACK_RATE_LIMITS.get(exchange, {"max_requests": 10, "window": 60})
        _local_limiters[exchange] = LocalRateLimiter(
            config["max_requests"],
            config["window"]
        )
    return _local_limiters[exchange]

async def check_rate_limit(exchange: str, identifier: str) -> bool:
    """
    检查是否允许请求

    Args:
        exchange: 交易所名称
        identifier: 标识符（API Key 或 IP）

    Returns:
        True 允许，False 拒绝
    """
    circuit_breaker = get_circuit_breaker()
    config = RATE_LIMITS.get(exchange)

    if not config:
        logger.warning(f"Unknown exchange: {exchange}, allowing request")
        return True

    # 尝试使用 Redis 限流
    if circuit_breaker.can_attempt():
        try:
            redis = await get_redis_client()
            script = redis.register_script(RATE_LIMIT_LUA_SCRIPT)

            key = f"ratelimit:{exchange}:{identifier}"
            now_ms = int(time.time() * 1000)
            window_seconds = config["window"]
            max_requests = config["max_requests"]
            request_id = uuid.uuid4().hex

            result = await script(
                keys=[key],
                args=[now_ms, window_seconds, max_requests, request_id]
            )

            circuit_breaker.record_success()
            allowed = bool(result)

            if not allowed:
                logger.warning(f"Rate limit exceeded (Redis): {exchange} {identifier}")

            return allowed

        except (RedisError, Exception) as e:
            logger.warning(f"Redis rate limit failed: {e}, falling back to local")
            circuit_breaker.record_failure()

    # 降级到本地限流器
    limiter = _get_local_limiter(exchange)
    allowed = limiter.is_allowed()

    if not allowed:
        logger.warning(f"Rate limit exceeded (local): {exchange} {identifier}")

    return allowed

def rate_limit(exchange: str, identifier_key: str = "symbol"):
    """
    限流装饰器

    Args:
        exchange: 交易所名称
        identifier_key: 从函数参数中提取标识符的键名

    Example:
        @rate_limit(exchange="binance", identifier_key="symbol")
        async def fetch_klines(symbol: str, ...):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 从函数签名提取参数
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # 获取标识符值
            identifier = bound.arguments.get(identifier_key, "default")

            # 检查限流
            allowed = await check_rate_limit(exchange, str(identifier))

            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            return await func(*args, **kwargs)

        return wrapper
    return decorator
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/services/test_rate_limiter.py::test_rate_limiter_allows_within_limit -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/config/rate_limits.py app/services/rate_limiter.py tests/services/test_rate_limiter.py
git commit -m "feat: add Redis-based rate limiter with local fallback"
```

### Task 7: 集成限流器到 API 客户端

**Files:**
- Modify: `app/services/binance_client.py:45-51`
- Modify: `app/okx/trading_client.py:97-100`
- Modify: `app/polygon/client.py:47-72`

- [ ] **Step 1: 为 Binance 客户端添加限流**

在 `fetch_binance_klines` 函数上添加装饰器：
```python
from app.services.rate_limiter import rate_limit

@rate_limit(exchange="binance", identifier_key="symbol")
async def fetch_binance_klines(
    symbol: str,
    interval: str,
    start_time: int,
    end_time: int,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    # 现有代码保持不变
    ...
```

- [ ] **Step 2: 为 OKX 客户端添加限流**

在 `OKXTradingClient` 类的 API 调用方法上添加装饰器（示例）：
```python
from app.services.rate_limiter import rate_limit

class OKXTradingClient:
    # ... 现有代码 ...

    @rate_limit(exchange="okx", identifier_key="api_key")
    async def get_balance(self, api_key: str = None) -> Dict[str, Any]:
        # 现有代码保持不变
        ...
```

- [ ] **Step 3: 为 Polygon 客户端添加限流**

在 `fetch_news` 函数上添加装饰器：
```python
from app.services.rate_limiter import rate_limit

@rate_limit(exchange="polygon", identifier_key="ticker")
async def fetch_news(ticker: str, ...) -> List[Dict[str, Any]]:
    # 现有代码保持不变
    ...
```

- [ ] **Step 4: 测试限流器集成**

Run: `uv run python -c "import asyncio; from app.services.binance_client import fetch_binance_klines; asyncio.run(fetch_binance_klines('BTCUSDT', '1m', 0, 0))"`
Expected: 正常执行（或 Rate limit 日志）

- [ ] **Step 5: Commit**

```bash
git add app/services/binance_client.py app/okx/trading_client.py app/polygon/client.py
git commit -m "feat: integrate rate limiter into API clients"
```

## 阶段 5：ARQ 任务队列

### Task 8: 创建 ARQ Worker 配置和任务

**Files:**
- Create: `app/tasks/worker_settings.py`
- Modify: `app/tasks/update_ohlc.py`
- Create: `tests/tasks/test_update_ohlc_arq.py`

- [ ] **Step 1: 写测试 - ARQ 任务执行**

```python
# tests/tasks/test_update_ohlc_arq.py
import pytest
from unittest.mock import AsyncMock, patch
from app.tasks.update_ohlc import update_daily_ohlc

@pytest.mark.asyncio
async def test_update_daily_ohlc_arq_task():
    """测试 ARQ 任务执行"""
    # 模拟 ARQ 上下文
    mock_redis = AsyncMock()
    ctx = {
        'redis': mock_redis,
        'job_id': 'test-job-123',
        'job_try': 1
    }

    # Mock 外部依赖
    with patch('app.tasks.update_ohlc.call_get_stock_history') as mock_get:
        with patch('app.tasks.update_ohlc.upsert_ohlc') as mock_upsert:
            mock_get.return_value = [{'date': '2024-01-01', 'close': 100}]

            # 执行任务
            result = await update_daily_ohlc(ctx)

            # 验证结果
            assert 'success' in result
            assert 'failed' in result
            assert 'total_records' in result
            assert result['success'] >= 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/tasks/test_update_ohlc_arq.py -v`
Expected: FAIL (函数签名不匹配)

- [ ] **Step 3: 创建 ARQ Worker 配置**

```python
# app/tasks/worker_settings.py
"""ARQ Worker 配置"""
import os
from arq.connections import RedisSettings

class WorkerSettings:
    """ARQ Worker 配置类"""

    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    # 任务函数列表（稍后添加）
    functions = []

    # 重试配置
    max_tries = 3
    retry_jobs = True
    job_timeout = int(os.getenv("ARQ_JOB_TIMEOUT", "600"))

    # 结果保留时间
    keep_result = int(os.getenv("ARQ_KEEP_RESULT", "3600"))
```

- [ ] **Step 2: 重构 update_ohlc 为 ARQ 任务**

修改 `app/tasks/update_ohlc.py`：
```python
"""Scheduled task to update OHLC data daily (ARQ version)."""
import logging
from datetime import datetime, timedelta
from app.mcp_client.finance_client import call_get_stock_history
from app.database import upsert_ohlc, update_metadata

logger = logging.getLogger(__name__)

SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']

async def update_daily_ohlc(ctx) -> dict:
    """ARQ 任务：更新每日 OHLC 数据

    Args:
        ctx: ARQ 上下文
            - ctx['redis']: Redis 连接池
            - ctx['job_id']: 任务 ID
            - ctx['job_try']: 重试次数

    Returns:
        dict: {"success": int, "failed": int, "total_records": int}
    """
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    start_date = yesterday.isoformat()
    end_date = today.isoformat()

    logger.info(f"[ARQ] Starting daily OHLC update for {start_date} to {end_date}")

    success_count = 0
    total_records = 0

    for symbol in SYMBOLS:
        try:
            data = call_get_stock_history(symbol, start_date, end_date)
            if data:
                upsert_ohlc(symbol, data)
                update_metadata(symbol, start_date, end_date)
                total_records += len(data)
                success_count += 1
                logger.info(f"✓ Updated {symbol}: {len(data)} records")
            else:
                logger.warning(f"✗ No data returned for {symbol}")
        except Exception as e:
            logger.error(f"✗ Failed to update {symbol}: {e}")

    result = {
        "success": success_count,
        "failed": len(SYMBOLS) - success_count,
        "total_records": total_records
    }

    logger.info(f"[ARQ] Daily update complete: {result}")
    return result
```

- [ ] **Step 3: 注册任务到 Worker 配置**

更新 `app/tasks/worker_settings.py`：
```python
from app.tasks.update_ohlc import update_daily_ohlc

class WorkerSettings:
    # ... 现有配置 ...

    functions = [update_daily_ohlc]
```

- [ ] **Step 4: 测试 ARQ Worker 启动**

Run: `uv run arq app.tasks.worker_settings.WorkerSettings --check`
Expected: Worker 配置验证通过

- [ ] **Step 5: Commit**

```bash
git add app/tasks/worker_settings.py app/tasks/update_ohlc.py
git commit -m "feat: migrate tasks to ARQ async queue"
```

### Task 9: 集成 ARQ 到 APScheduler

**Files:**
- Create: `app/scheduler.py`

- [ ] **Step 1: 创建调度器模块**

```python
# app/scheduler.py
"""APScheduler + ARQ 集成"""
import logging
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from arq import create_pool
from arq.connections import RedisSettings

logger = logging.getLogger(__name__)

# 全局 ARQ 连接池
_arq_pool = None

async def init_arq_pool():
    """初始化 ARQ 连接池"""
    global _arq_pool
    if _arq_pool is None:
        redis_settings = RedisSettings.from_dsn(
            os.getenv("REDIS_URL", "redis://localhost:6379/0")
        )
        _arq_pool = await create_pool(redis_settings)
        logger.info("ARQ pool initialized")
    return _arq_pool

async def schedule_daily_update():
    """定时任务：每日 OHLC 更新"""
    pool = await init_arq_pool()
    job = await pool.enqueue_job('update_daily_ohlc')
    logger.info(f"Enqueued daily OHLC update task: {job.job_id}")

def setup_scheduler():
    """设置定时任务"""
    scheduler = AsyncIOScheduler()

    # 每天凌晨 2 点执行
    scheduler.add_job(
        schedule_daily_update,
        'cron',
        hour=2,
        minute=0,
        id='daily_ohlc_update'
    )

    logger.info("Scheduler configured")
    return scheduler
```

- [ ] **Step 2: 在 FastAPI 启动时初始化调度器**

在 `app/api/main.py` 的 `lifespan` 中添加：
```python
from app.scheduler import setup_scheduler, init_arq_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 ARQ
    await init_arq_pool()

    # 启动调度器
    scheduler = setup_scheduler()
    scheduler.start()

    yield

    # 关闭调度器
    scheduler.shutdown()
```

- [ ] **Step 3: 测试调度器**

Run: `uv run uvicorn app.api.main:app --port 8080`
Expected: 服务启动，调度器日志显示

- [ ] **Step 4: Commit**

```bash
git add app/scheduler.py app/api/main.py
git commit -m "feat: integrate ARQ with APScheduler"
```

## 阶段 6：集成测试和文档

### Task 10: 端到端集成测试

**Files:**
- Create: `tests/integration/test_redis_integration.py`

- [ ] **Step 1: 创建集成测试**

```python
# tests/integration/test_redis_integration.py
"""Redis 集成端到端测试"""
import pytest
import pandas as pd
from app.services.hot_cache import get_hot_cache, set_hot_cache
from app.services.rate_limiter import check_rate_limit
from app.services.redis_client import get_redis_client

@pytest.mark.asyncio
async def test_full_redis_integration():
    """测试 Redis 完整集成流程"""
    # 1. 测试 Redis 连接
    redis = await get_redis_client()
    await redis.ping()

    # 2. 测试缓存读写
    test_data = pd.DataFrame({
        'timestamp': [1234567890000],
        'close': [50000.0]
    })
    await set_hot_cache("TESTBTC", "1m", test_data, ttl=60)
    result = await get_hot_cache("TESTBTC", "1m")
    assert not result.empty

    # 3. 测试限流器
    allowed = await check_rate_limit("binance", "test_integration")
    assert allowed is True

    # 清理
    await redis.delete("cache:kline:TESTBTC:1m:latest")
    await redis.delete("ratelimit:binance:test_integration")

@pytest.mark.asyncio
async def test_redis_failover():
    """测试 Redis 故障切换"""
    from app.services.redis_client import get_circuit_breaker
    from app.services.hot_cache import set_hot_cache, get_hot_cache
    import pandas as pd

    # 模拟 Redis 故障（触发熔断器）
    cb = get_circuit_breaker()
    for _ in range(5):
        cb.record_failure()

    assert cb.state.value == "open"

    # 在降级模式下写入缓存
    test_data = pd.DataFrame({'timestamp': [123], 'close': [100.0]})
    await set_hot_cache("TESTFAIL", "1m", test_data, ttl=60)

    # 应该能从内存缓存读取
    result = await get_hot_cache("TESTFAIL", "1m")
    assert not result.empty
    assert result['close'].iloc[0] == 100.0

    # 恢复 Redis（模拟）
    cb.record_success()
    assert cb.state.value == "closed"
```

- [ ] **Step 2: 运行集成测试**

Run: `uv run pytest tests/integration/test_redis_integration.py -v`
Expected: 所有测试通过

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_redis_integration.py
git commit -m "test: add end-to-end Redis integration tests"
```

### Task 11: 更新文档和 README

**Files:**
- Modify: `README.md`
- Create: `docs/redis-setup.md`

- [ ] **Step 1: 创建 Redis 设置文档**

```markdown
# docs/redis-setup.md
# Redis 设置指南

## 本地开发

### 启动 Redis
\`\`\`bash
docker-compose up -d redis
\`\`\`

### 验证 Redis 运行
\`\`\`bash
docker-compose logs redis
\`\`\`

### 启动 ARQ Worker
\`\`\`bash
uv run arq app.tasks.worker_settings.WorkerSettings
\`\`\`

## 生产部署

### 环境变量配置
\`\`\`bash
REDIS_URL=rediss://your-redis-host:6380/0
REDIS_ENABLED=true
INSTANCE_COUNT=4
\`\`\`

### 监控
- Redis 连接状态：检查应用日志中的 "Circuit breaker" 消息
- 缓存命中率：检查 "Cache HIT/MISS" 日志
- 限流触发：检查 "Rate limit exceeded" 日志

## 故障排查

### Redis 连接失败
- 检查 Docker 容器状态：`docker-compose ps`
- 检查 Redis 日志：`docker-compose logs redis`
- 验证环境变量：`echo $REDIS_URL`

### 熔断器触发
- 系统会自动降级到内存缓存
- 每 30 秒尝试恢复 Redis 连接
- 检查日志：`grep "Circuit breaker" app.log`
\`\`\`

- [ ] **Step 2: 更新 README.md**

在 README.md 中添加 Redis 相关章节：
```markdown
## Redis 集成

本项目使用 Redis 实现：
- 分布式缓存（K 线数据）
- API 限流（防止交易所封禁）
- 异步任务队列（ARQ）

### 快速开始
\`\`\`bash
# 启动 Redis
docker-compose up -d redis

# 启动 ARQ Worker
uv run arq app.tasks.worker_settings.WorkerSettings

# 启动 API 服务
uv run uvicorn app.api.main:app --port 8080
\`\`\`

详细文档：[Redis 设置指南](docs/redis-setup.md)
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/redis-setup.md
git commit -m "docs: add Redis setup guide and update README"
```

---

## 验收标准

完成所有任务后，系统应满足：

1. ✅ Redis 容器正常运行
2. ✅ 缓存层支持 Redis 优先 + 内存降级
3. ✅ 限流器正常工作（Redis + 本地降级）
4. ✅ ARQ Worker 可以执行异步任务
5. ✅ 熔断器在 Redis 故障时自动降级
6. ✅ 所有单元测试和集成测试通过
7. ✅ 文档完整（设置指南 + README）

## 后续优化（可选）

- 添加 Redis Sentinel 支持（高可用）
- 集成 Prometheus 监控指标
- 添加 Redis 缓存预热脚本
- 实现缓存失效策略（Pub/Sub）






