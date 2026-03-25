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
- **任务队列**：`rq` - 轻量级 Redis 任务队列
- **连接池**：`redis.asyncio.ConnectionPool` - 异步连接池管理
- **序列化**：JSON（Pydantic 模型支持）

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

**Circuit Breaker 模式**：

```python
状态机：
CLOSED (正常) → OPEN (故障) → HALF_OPEN (探测) → CLOSED

- CLOSED: Redis 正常，所有请求走 Redis
- OPEN: Redis 故障，所有请求走内存缓存
- HALF_OPEN: 定期探测 Redis，成功则恢复 CLOSED
```

**参数配置**：
- 失败阈值：连续 5 次失败触发 OPEN
- 超时时间：Redis 操作超时 2 秒
- 恢复探测：每 30 秒尝试一次 PING
- 半开窗口：允许 3 次探测请求

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

**K 线数据（DataFrame）**：
```python
# 写入 Redis
df.to_json(orient='records') → JSON 字符串 → Redis

# 从 Redis 读取
Redis → JSON 字符串 → pd.DataFrame(json.loads(data))
```

**Pydantic 模型**：
```python
# 写入 Redis
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

**Redis 不可用时**：
- 使用本地内存计数器（`collections.deque`）
- 仅限当前进程，无法跨实例共享
- 日志记录降级状态，便于监控

**实现**：
```python
# 降级到本地限流器
local_limiter = {
    "binance": deque(maxlen=1200),  # 最多保留 1200 条记录
    "okx": deque(maxlen=20),
    "polygon": deque(maxlen=5),
}
```


## RQ 任务队列设计

### 架构概览

```
┌──────────────────┐
│  APScheduler     │  定时触发器（每天凌晨 2 点）
└────────┬─────────┘
         │ enqueue_task()
         ▼
┌──────────────────┐
│   Redis Queue    │  任务队列（持久化）
└────────┬─────────┘
         │ fetch_job()
         ▼
┌──────────────────┐
│   RQ Worker      │  后台执行器（支持重试）
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Task Function   │  实际业务逻辑
│  (update_ohlc)   │
└──────────────────┘
```

### 与 APScheduler 的配合

**职责划分**：
- **APScheduler**：负责定时触发（cron 表达式）
- **RQ**：负责异步执行（长耗时任务）

**示例**：
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from rq import Queue
from redis import Redis

scheduler = AsyncIOScheduler()
redis_conn = Redis(host='localhost', port=6379)
queue = Queue('default', connection=redis_conn)

# APScheduler 定时触发，将任务推送到 RQ
@scheduler.scheduled_job('cron', hour=2, minute=0)
def schedule_daily_update():
    queue.enqueue('app.tasks.update_ohlc.update_daily_ohlc')
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

**任务函数签名**：
```python
# app/tasks/update_ohlc.py
def update_daily_ohlc() -> dict:
    """RQ 任务：更新每日 OHLC 数据
    
    Returns:
        dict: {"success": int, "failed": int, "total_records": int}
    """
    # 业务逻辑
    return {"success": 7, "failed": 0, "total_records": 1234}
```

### 重试策略

**配置**：
```python
from rq import Retry

queue.enqueue(
    'app.tasks.update_ohlc.update_daily_ohlc',
    retry=Retry(max=3, interval=[60, 300, 900])  # 1分钟、5分钟、15分钟
)
```

**失败处理**：
- 任务失败后自动重试（最多 3 次）
- 重试间隔递增（指数退避）
- 最终失败后记录到 `failed` 队列
- 支持手动重新入队

### Worker 配置

**启动命令**：
```bash
# 启动单个 worker
uv run rq worker default --with-scheduler

# 启动多个 worker（生产环境）
uv run rq worker default high low --burst
```

**Worker 配置文件**（`app/config/rq_config.py`）：
```python
RQ_CONFIG = {
    "default_timeout": 600,  # 10 分钟超时
    "result_ttl": 3600,      # 结果保留 1 小时
    "failure_ttl": 86400,    # 失败记录保留 24 小时
}
```

**队列优先级**：
- `high`: 实时任务（账户查询、下单）
- `default`: 常规任务（数据更新）
- `low`: 批量任务（历史数据回填）


## 实现清单

### 文件清单

**新增文件**：
```
app/services/redis_client.py       # Redis 连接客户端（健康检查、连接池）
app/services/rate_limiter.py       # 限流装饰器和逻辑
app/config/rate_limits.py          # 限流配置
app/config/rq_config.py            # RQ 配置
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
    "rq>=1.16.0",                  # Redis Queue 任务队列
    "hiredis>=2.3.0",              # Redis 协议加速（可选）
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
REDIS_MAX_CONNECTIONS=50
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=5

# Redis 健康检查
REDIS_HEALTH_CHECK_INTERVAL=30

# 是否启用 Redis（false 时使用内存缓存）
REDIS_ENABLED=true

# ============================================
# RQ 任务队列配置
# ============================================
# RQ Worker 数量
RQ_WORKER_COUNT=2

# RQ 任务超时（秒）
RQ_DEFAULT_TIMEOUT=600

# RQ 结果保留时间（秒）
RQ_RESULT_TTL=3600
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
3. RQ 任务的重试和失败处理
4. 缓存 TTL 过期行为
5. Circuit Breaker 状态转换

### 监控和日志

**关键指标**：
- Redis 连接状态（健康/降级）
- 缓存命中率（Redis/内存）
- 限流触发次数（按交易所）
- RQ 任务成功/失败率
- Redis 内存使用率

**日志级别**：
- INFO: 正常操作（缓存命中、任务完成）
- WARNING: 降级事件（Redis 不可用）
- ERROR: 失败操作（任务失败、限流异常）

