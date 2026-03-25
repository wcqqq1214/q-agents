# Redis 集成设计文档

## 项目背景

Finance Agent 是一个基于大语言模型的金融智能体项目，目前系统在频繁调用第三方交易所 API（OKX, Binance, Polygon）时存在以下问题：

1. **响应延迟**：外部 API 调用延迟影响用户体验
2. **Rate Limit 风险**：频繁请求导致 HTTP 429 错误，面临被交易所封禁的风险
3. **前端压力**：K 线图的高频数据请求给后端带来压力
4. **单点瓶颈**：现有内存缓存仅限单进程，无法跨实例共享

## 核心目标

通过引入 Redis 实现以下目标：

1. **分布式缓存**：替换/增强现有本地缓存，支持多实例部署
2. **API 限流**：基于 Redis 的全局限流器，防止交易所封禁
3. **异步任务队列**：使用 RQ 处理长耗时爬虫任务，避免阻塞主流程
4. **优雅降级**：Redis 不可用时自动回退到内存缓存，保证系统可用性

## 整体架构

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐      ┌──────────────────┐            │
│  │  Cache Service   │      │  Rate Limiter    │            │
│  │  (hot_cache.py)  │      │ (rate_limiter.py)│            │
│  └────────┬─────────┘      └────────┬─────────┘            │
│           │                         │                        │
│           └─────────┬───────────────┘                        │
│                     │                                        │
│           ┌─────────▼──────────┐                            │
│           │   Redis Client     │                            │
│           │ (redis_client.py)  │                            │
│           └─────────┬──────────┘                            │
│                     │                                        │
│        ┌────────────┼────────────┐                          │
│        │            │            │                          │
│   [正常模式]    [降级模式]   [任务队列]                      │
│        │            │            │                          │
│    ┌───▼───┐   ┌───▼────┐   ┌──▼────┐                     │
│    │ Redis │   │ Memory │   │  RQ   │                      │
│    │ Cache │   │ Cache  │   │Worker │                      │
│    └───────┘   └────────┘   └───────┘                      │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 技术选型

- **Redis 客户端**：`redis[asyncio]` - 异步 Redis 客户端
- **任务队列**：`arq` - 原生异步 Redis 任务队列（与 FastAPI 完美契合）
- **连接池**：`redis.asyncio.ConnectionPool` - 异步连接池管理
- **序列化**：
  - K 线数据（DataFrame）：MessagePack 或 Parquet（高性能二进制格式）
  - Pydantic 模型：JSON（保持可读性）

### 部署策略

- **开发环境**：Docker Compose 本地 Redis
- **生产环境**：支持切换到云端托管 Redis（通过环境变量配置）
- **连接方式**：支持 `redis://` 和 `rediss://`（TLS）


## 缓存层详细设计

### 缓存策略：Redis 优先 + 内存容灾

**核心原则**：
- **正常模式**：只使用 Redis，完全绕过内存缓存
- **降级模式**：仅当 Redis 不可用时，才回退到内存缓存
- **避免双写**：不维护双层缓存同步，避免一致性问题

### 数据流

```
┌─────────────────┐
│  请求到达        │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ 尝试读取 Redis       │
└────────┬────────────┘
         │
    ┌────┴────┐
    │         │
[成功]    [Redis 异常]
    │         │
    │         ▼
    │    ┌─────────────────┐
    │    │ 捕获异常         │
    │    │ 标记降级状态     │
    │    └────────┬────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 读取内存缓存     │
    │    └────────┬────────┘
    │             │
    │        ┌────┴────┐
    │        │         │
    │    [命中]    [未命中]
    │        │         │
    └────────┴─────────┘
             │
             ▼
    ┌─────────────────┐
    │ 返回数据 或      │
    │ 调用交易所 API   │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ 写入 Redis       │
    │ (若可用)         │
    │ 或写入内存       │
    │ (若降级)         │
    └─────────────────┘
```

### 健康检查机制

**Circuit Breaker 模式（本地状态机）**：

```python
状态机：
CLOSED (正常) → OPEN (故障) → HALF_OPEN (探测) → CLOSED

- CLOSED: Redis 正常，所有请求走 Redis
- OPEN: Redis 故障，所有请求走内存缓存
- HALF_OPEN: 定期探测 Redis，成功则恢复 CLOSED
```

**关键设计原则**：
- ⚠️ **熔断器状态必须维护在进程本地内存**（不能存 Redis，否则逻辑悖论）
- 每个 FastAPI 实例独立维护自己的熔断器状态
- 使用 Python 内存变量（如 `CircuitBreakerState` 类）

**参数配置**：
- 失败阈值：连续 5 次失败触发 OPEN
- 超时时间：Redis 操作超时 2 秒（包含连接超时 + 读写超时）
- 连接池超时：等待获取连接最多 1 秒（超时立即降级）
- 恢复探测：每 30 秒尝试一次 PING
- 半开窗口：允许 3 次探测请求

**降级恢复时的缓存清理**：
- 当熔断器从 OPEN 恢复到 CLOSED 时，主动清空本地内存缓存
- 接受短时间的 Cache Miss，避免返回过期数据

### TTL 策略

不同数据类型的过期时间：

| 数据类型 | TTL | 说明 |
|---------|-----|------|
| K 线数据（1 分钟） | 60 秒 | 高频更新 |
| K 线数据（5 分钟） | 300 秒 | 中频更新 |
| K 线数据（1 小时） | 3600 秒 | 低频更新 |
| K 线数据（1 天） | 86400 秒 | 历史数据 |
| 账户余额 | 30 秒 | 实时性要求高 |
| 市场行情 | 10 秒 | 实时性要求高 |
| 新闻数据 | 1800 秒 | 30 分钟 |

### 序列化方案

**K 线数据（DataFrame）- 高性能方案**：
```python
# 方案 1: MessagePack（推荐，速度快 10 倍于 JSON）
import msgpack
import pandas as pd

# 写入 Redis
data_dict = df.to_dict(orient='records')
serialized = msgpack.packb(data_dict, use_bin_type=True)
await redis.set(key, serialized)

# 从 Redis 读取
data = await redis.get(key)
data_dict = msgpack.unpackb(data, raw=False)
df = pd.DataFrame(data_dict)

# 方案 2: Parquet（最高压缩率，适合大数据集）
import io

# 写入 Redis
buffer = io.BytesIO()
df.to_parquet(buffer, engine='pyarrow', compression='snappy')
await redis.set(key, buffer.getvalue())

# 从 Redis 读取
data = await redis.get(key)
df = pd.read_parquet(io.BytesIO(data))
```

**性能对比**（1000 行 K 线数据）：
| 方案 | 序列化时间 | 反序列化时间 | 存储大小 |
|------|-----------|-------------|---------|
| JSON | ~15ms | ~20ms | 150KB |
| MessagePack | ~2ms | ~3ms | 120KB |
| Parquet | ~5ms | ~4ms | 80KB |

**Pydantic 模型**：
```python
# 写入 Redis（保持 JSON 可读性）
model.model_dump_json() → JSON 字符串 → Redis

# 从 Redis 读取
Redis → JSON 字符串 → ModelClass.model_validate_json(data)
```

### Key 命名规范

```
cache:{data_type}:{symbol}:{interval}:{params_hash}

示例：
- cache:kline:BTCUSDT:1m:latest
- cache:kline:ETHUSDT:5m:20260325
- cache:balance:okx:demo:account1
- cache:ticker:binance:BTCUSDT
```


## 限流器详细设计

### 滑动窗口算法（Redis Sorted Set）

**数据结构**：
```
Key: ratelimit:{exchange}:{identifier}
Type: Sorted Set (ZSET)
Score: 时间戳（毫秒）
Member: 请求唯一 ID（UUID）
```

**算法流程**：
```python
1. 获取当前时间戳 now_ms
2. 计算窗口起始时间 window_start = now_ms - window_ms
3. 删除窗口外的旧记录：ZREMRANGEBYSCORE key 0 window_start
4. 统计窗口内请求数：ZCARD key
5. 判断是否超限：
   - 若 count < max_requests: 允许请求，添加新记录 ZADD key now_ms uuid
   - 若 count >= max_requests: 拒绝请求，返回 429
6. 设置 key 过期时间：EXPIRE key window_seconds
```

**原子性保证**：
使用 Redis Lua 脚本确保操作原子性，避免竞态条件。

### 交易所限流配置

| 交易所 | 限制 | 窗口 | 标识符 |
|--------|------|------|--------|
| Binance | 1200 请求 | 60 秒 | API Key 或 IP |
| OKX | 20 请求 | 1 秒 | API Key |
| Polygon | 5 请求 | 60 秒 | API Key |

**配置文件**（`app/config/rate_limits.py`）：
```python
RATE_LIMITS = {
    "binance": {"max_requests": 1200, "window": 60},
    "okx": {"max_requests": 20, "window": 1},
    "polygon": {"max_requests": 5, "window": 60},
}
```

### 装饰器用法

**异步函数装饰器**：
```python
from app.services.rate_limiter import rate_limit

@rate_limit(exchange="binance", identifier_key="symbol")
async def fetch_binance_klines(symbol: str, interval: str, ...):
    """Binance API 调用会自动限流"""
    ...

@rate_limit(exchange="okx", identifier_key="api_key")
async def okx_get_balance(api_key: str):
    """OKX API 调用会自动限流"""
    ...
```

**手动调用**：
```python
from app.services.rate_limiter import check_rate_limit, record_request

# 检查是否允许请求
allowed = await check_rate_limit("binance", "BTCUSDT")
if not allowed:
    raise HTTPException(status_code=429, detail="Rate limit exceeded")

# 执行请求
result = await external_api_call()

# 记录请求（可选，装饰器会自动记录）
await record_request("binance", "BTCUSDT")
```

### 降级策略

**⚠️ 关键风险：多实例放大效应**

当 Redis 不可用时，如果每个实例都使用全局配额的本地限流器，会导致实际请求量 = 配额 × 实例数，触发交易所封禁。

**保守降级方案**：

```python
import os
from collections import deque
from time import time

# 从环境变量读取实例数量（默认 4）
INSTANCE_COUNT = int(os.getenv("INSTANCE_COUNT", "4"))

# 降级时的本地限流配置（全局配额 / 实例数）
FALLBACK_RATE_LIMITS = {
    "binance": {
        "max_requests": 1200 // INSTANCE_COUNT,  # 300 请求/实例
        "window": 60
    },
    "okx": {
        "max_requests": 20 // INSTANCE_COUNT,    # 5 请求/实例
        "window": 1
    },
    "polygon": {
        "max_requests": 5 // INSTANCE_COUNT,     # 1-2 请求/实例
        "window": 60
    },
}

class LocalRateLimiter:
    """本地滑动窗口限流器（降级使用）"""
    def __init__(self, max_requests: int, window: int):
        self.max_requests = max_requests
        self.window = window
        self.requests = deque()  # 存储时间戳

    def is_allowed(self) -> bool:
        now = time()
        # 移除窗口外的请求
        while self.requests and self.requests[0] < now - self.window:
            self.requests.popleft()

        # 检查是否超限
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False
```

**降级日志和监控**：
```python
import logging

logger.warning(
    f"Rate limiter degraded to local mode. "
    f"Quota reduced to {max_requests}/{window}s per instance. "
    f"Total cluster capacity: ~{max_requests * INSTANCE_COUNT}/{window}s"
)
```


## ARQ 任务队列设计

### 架构概览

```
┌──────────────────┐
│  APScheduler     │  定时触发器（每天凌晨 2 点）
└────────┬─────────┘
         │ await enqueue_job()
         ▼
┌──────────────────┐
│   Redis Queue    │  任务队列（持久化）
│   (ARQ)          │
└────────┬─────────┘
         │ fetch_job()
         ▼
┌──────────────────┐
│   ARQ Worker     │  异步后台执行器（原生 asyncio）
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Async Task      │  实际业务逻辑（无需 asyncio.run 包装）
│  (update_ohlc)   │
└──────────────────┘
```

### 为什么选择 ARQ 而非 RQ

| 特性 | RQ | ARQ |
|------|----|----|
| 异步支持 | ❌ 需要 asyncio.run() 包装 | ✅ 原生 asyncio |
| FastAPI 集成 | ⚠️ 事件循环冲突风险 | ✅ 完美契合 |
| 性能 | 同步阻塞 | 高并发异步 |
| 连接池复用 | ❌ 无法复用 FastAPI 的连接池 | ✅ 共享连接池 |

### 与 APScheduler 的配合

**职责划分**：
- **APScheduler**：负责定时触发（cron 表达式）
- **ARQ**：负责异步执行（长耗时任务）

**示例**：
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from arq import create_pool
from arq.connections import RedisSettings

scheduler = AsyncIOScheduler()

# 初始化 ARQ
redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL"))
arq_pool = await create_pool(redis_settings)

# APScheduler 定时触发，将任务推送到 ARQ
@scheduler.scheduled_job('cron', hour=2, minute=0)
async def schedule_daily_update():
    await arq_pool.enqueue_job('update_daily_ohlc')
    logger.info("Enqueued daily OHLC update task")
```

### 任务定义

**任务模块**（`app/tasks/`）：
```
app/tasks/
├── __init__.py
├── update_ohlc.py       # 每日 OHLC 更新
├── daily_harvester.py   # 批量数据抓取
└── generate_reports.py  # 报告生成
```

**ARQ 任务函数签名（原生异步）**：
```python
# app/tasks/update_ohlc.py
async def update_daily_ohlc(ctx) -> dict:
    """ARQ 任务：更新每日 OHLC 数据

    Args:
        ctx: ARQ 上下文（包含 Redis 连接等）

    Returns:
        dict: {"success": int, "failed": int, "total_records": int}
    """
    # 直接使用 async/await，无需包装
    data = await call_get_stock_history(...)
    await upsert_ohlc(symbol, data)

    return {"success": 7, "failed": 0, "total_records": 1234}
```

### 重试策略

**ARQ 配置**：
```python
# app/tasks/__init__.py
from arq.connections import RedisSettings

class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL"))

    functions = [update_daily_ohlc, daily_harvester]

    # 重试配置
    max_tries = 3
    retry_jobs = True
    job_timeout = 600  # 10 分钟超时

    # 结果保留时间
    keep_result = 3600  # 1 小时
```

**失败处理**：
- 任务失败后自动重试（最多 3 次）
- ARQ 自动处理重试间隔
- 失败任务记录在 Redis 中，可通过 ARQ 监控工具查看

### Worker 配置

**启动命令**：
```bash
# 启动 ARQ worker
uv run arq app.tasks.WorkerSettings

# 生产环境（多 worker）
uv run arq app.tasks.WorkerSettings --burst
```

**Worker 配置**（已在 WorkerSettings 中定义）：
- 任务超时：600 秒（10 分钟）
- 结果保留：3600 秒（1 小时）
- 最大重试：3 次


## 实现清单

### 文件清单

**新增文件**：
```
app/services/redis_client.py       # Redis 连接客户端（健康检查、连接池）
app/services/rate_limiter.py       # 限流装饰器和逻辑
app/config/rate_limits.py          # 限流配置
app/tasks/worker_settings.py       # ARQ Worker 配置
docker-compose.yml                 # Docker Compose 配置（Redis）
```

**修改文件**：
```
app/services/hot_cache.py          # 重构为 Redis 优先 + 内存容灾
app/config_manager.py              # 添加 Redis 配置管理
app/okx/trading_client.py          # 添加限流装饰器
app/services/binance_client.py     # 添加限流装饰器
app/polygon/client.py              # 添加限流装饰器
app/tasks/update_ohlc.py           # 适配 RQ 任务格式
pyproject.toml                     # 添加 Redis 和 RQ 依赖
.env.example                       # 添加 Redis 配置项
```

### 依赖更新

**pyproject.toml**：
```toml
dependencies = [
    # ... 现有依赖 ...
    "redis[asyncio]>=5.0.0",       # Redis 异步客户端
    "arq>=0.26.0",                 # ARQ 异步任务队列
    "hiredis>=2.3.0",              # Redis 协议加速（可选）
    "msgpack>=1.0.0",              # MessagePack 序列化（高性能）
    "pyarrow>=15.0.0",             # Parquet 支持（可选）
]
```

### 环境变量配置

**.env.example 新增**：
```bash
# ============================================
# Redis 配置
# ============================================
# Redis 连接 URL
# 本地开发: redis://localhost:6379/0
# 生产环境: rediss://your-redis-host:6380/0 (TLS)
REDIS_URL=redis://localhost:6379/0

# Redis 连接池配置
REDIS_MAX_CONNECTIONS=100
REDIS_SOCKET_TIMEOUT=2
REDIS_SOCKET_CONNECT_TIMEOUT=2
REDIS_POOL_TIMEOUT=1

# Redis 健康检查
REDIS_HEALTH_CHECK_INTERVAL=30

# 是否启用 Redis（false 时使用内存缓存）
REDIS_ENABLED=true

# ============================================
# 限流器配置
# ============================================
# 实例数量（用于降级时的配额分配）
INSTANCE_COUNT=4

# ============================================
# ARQ 任务队列配置
# ============================================
# ARQ Worker 数量
ARQ_WORKER_COUNT=2

# ARQ 任务超时（秒）
ARQ_JOB_TIMEOUT=600

# ARQ 结果保留时间（秒）
ARQ_KEEP_RESULT=3600
```

### Docker Compose 配置

**docker-compose.yml**：
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

**启动命令**：
```bash
# 启动 Redis
docker-compose up -d redis

# 查看日志
docker-compose logs -f redis

# 停止 Redis
docker-compose down
```

### ConfigManager 更新

**app/config_manager.py 新增方法**：
```python
def get_redis_settings(self) -> Dict[str, Optional[str]]:
    """获取 Redis 配置"""
    return {
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        "redis_enabled": os.getenv("REDIS_ENABLED", "true").lower() == "true",
        "max_connections": int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
    }

def update_redis_settings(self, redis_url: Optional[str] = None, 
                         redis_enabled: Optional[bool] = None) -> Dict:
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

### 测试策略

**单元测试**：
```
tests/services/test_redis_client.py      # Redis 客户端测试
tests/services/test_hot_cache.py         # 缓存层测试（含降级）
tests/services/test_rate_limiter.py      # 限流器测试
tests/tasks/test_update_ohlc.py          # RQ 任务测试
```

**集成测试**：
```
tests/integration/test_redis_failover.py # Redis 故障切换测试
tests/integration/test_rate_limit_e2e.py # 端到端限流测试
```

**测试覆盖重点**：
1. Redis 连接失败时的降级行为
2. 限流器在高并发下的准确性
3. ARQ 任务的重试和失败处理
4. 缓存 TTL 过期行为
5. Circuit Breaker 状态转换
6. 多实例降级时的配额分配

### 监控和日志

**关键指标**：
- Redis 连接状态（健康/降级）
- 缓存命中率（Redis/内存）
- 限流触发次数（按交易所）
- ARQ 任务成功/失败率
- Redis 内存使用率
- 连接池等待时间

**日志级别**：
- INFO: 正常操作（缓存命中、任务完成）
- WARNING: 降级事件（Redis 不可用、限流降级）
- ERROR: 失败操作（任务失败、连接超时）


## 技术细节补充

### 限流装饰器实现细节

**参数提取机制**：
```python
import functools
import inspect

def rate_limit(exchange: str, identifier_key: str = "symbol"):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 从函数签名提取参数
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # 获取标识符值
            identifier = bound.arguments.get(identifier_key, "default")
            
            # 检查限流
            await check_rate_limit(exchange, identifier)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
```

### Circuit Breaker 状态持久化

**多实例部署方案**：
- Circuit Breaker 状态存储在 Redis 中（共享状态）
- Key: `circuit_breaker:{service}:state`
- 值: `{"state": "OPEN", "failures": 5, "last_failure": 1234567890}`
- TTL: 300 秒（5 分钟）

### Circuit Breaker 状态持久化（修正版）

**⚠️ 关键修正：本地状态机，避免逻辑悖论**

熔断器状态必须维护在进程本地内存，不能存储在 Redis 中（否则 Redis 宕机时无法读取状态）。

**实现**：
```python
from enum import Enum
from datetime import datetime, timedelta

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """本地熔断器（每个实例独立维护）"""
    def __init__(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.next_retry_time = None

    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

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
            if datetime.now() >= self.next_retry_time:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        else:  # HALF_OPEN
            return True
```

### 限流 Lua 脚本（优化版）

**原子性保证 + 毫秒级精度**：
```lua
-- rate_limit.lua
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
    -- 使用 PEXPIRE 毫秒级精度
    redis.call('PEXPIRE', key, window * 1000)
    return 1  -- 允许
else
    return 0  -- 拒绝
end
```

**Python 调用**：
```python
script = redis.register_script(lua_script)
allowed = await script(
    keys=[f"ratelimit:{exchange}:{identifier}"],
    args=[now_ms, window_seconds, max_requests, uuid.uuid4().hex]
)
```

### Key 命名和哈希

**参数哈希生成**：
```python
import hashlib
import json

def generate_cache_key(data_type: str, symbol: str, interval: str, **params) -> str:
    """生成缓存 key"""
    # 标准化参数（排序确保一致性）
    params_str = json.dumps(params, sort_keys=True)
    params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]

    return f"cache:{data_type}:{symbol}:{interval}:{params_hash}"

# 示例
key = generate_cache_key("kline", "BTCUSDT", "1m", start_time=1234567890)
# 结果: cache:kline:BTCUSDT:1m:a3f2b1c4
```
