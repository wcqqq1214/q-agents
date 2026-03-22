# 加密货币 K 线数据冷热分离架构设计

## 概述

本设计采用 Lambda 架构变体，实现加密货币历史数据与实时数据的冷热分离存储与查询。通过 Binance Vision 离线数据包提供历史数据的绝对准确性，通过 Binance REST API 提供当天实时数据，在查询层无缝合并两者。

**设计目标：**
- 历史数据绝对纯净（Single Source of Truth）
- 实时数据低延迟（60 秒更新）
- 系统简单可靠（单机部署，无外部依赖）
- 容灾能力强（优雅降级，数据不丢失）

## 整体架构

### 三层架构

**1. 冷数据层（Cold Layer - Batch Processing）**
- **存储**：SQLite `crypto_ohlc` 表
- **数据范围**：历史数据（T-1 及之前）
- **数据源**：Binance Vision 官方归档（data.binance.vision）
- **更新频率**：每天一次（UTC 08:00 或更晚）
- **数据格式**：CSV（ZIP 压缩）
- **特点**：绝对准确，不可变，作为 Single Source of Truth

**2. 热数据层（Hot Layer - Speed Processing）**
- **存储**：Python 进程内存（全局字典 + pandas DataFrame）
- **数据范围**：最近 48 小时（昨天 + 今天）
- **数据源**：Binance REST API
- **更新频率**：每 60 秒
- **冷启动**：应用启动时一次性拉取今天所有数据
- **特点**：低延迟，允许重叠，自动过期

**3. 聚合层（Serving Layer）**
- **位置**：FastAPI 路由层
- **功能**：根据查询日期范围，自动拼接冷热数据
- **去重策略**：按 timestamp 去重，热数据优先
- **返回格式**：统一的 JSON 数组

### 数据流向

```
Binance Vision (历史 ZIP)  →  SQLite (冷数据)
                                        ↘
                                         API 响应 (拼接去重)
                                        ↗
Binance REST API (实时)     →  内存缓存 (热数据)
```

## 数据结构与存储

### 1. 冷数据存储（SQLite）

**表结构（现有）：**
```sql
CREATE TABLE crypto_ohlc (
    symbol        TEXT NOT NULL,      -- 交易对，如 "BTC-USDT"
    timestamp     INTEGER NOT NULL,   -- Unix 毫秒时间戳（UTC）
    date          TEXT NOT NULL,      -- ISO 8601 格式，如 "2024-01-01T00:00:00+00:00"
    open          REAL,               -- 开盘价
    high          REAL,               -- 最高价
    low           REAL,               -- 最低价
    close         REAL,               -- 收盘价
    volume        REAL,               -- 成交量
    bar           TEXT NOT NULL,      -- 时间间隔，如 "1m", "15m", "1H", "1D"
    PRIMARY KEY (symbol, timestamp, bar)
);

CREATE INDEX idx_crypto_ohlc_symbol_date ON crypto_ohlc(symbol, date DESC);
CREATE INDEX idx_crypto_ohlc_symbol_bar_date ON crypto_ohlc(symbol, bar, date DESC);
```

**设计要点：**
- `PRIMARY KEY (symbol, timestamp, bar)` 从数据库层面防止重复数据
- `timestamp` 使用 Unix 毫秒时间戳，无时区概念，便于比较和排序
- `date` 使用 ISO 8601 格式带时区后缀，便于人类阅读和调试
- 索引优化查询性能

### 2. 热数据存储（内存）

**全局缓存结构：**
```python
from typing import Dict
import pandas as pd

# 全局热缓存：{symbol: {bar: DataFrame}}
# 保留最近 48 小时数据（昨天 + 今天）
HOT_CACHE: Dict[str, Dict[str, pd.DataFrame]] = {
    "BTCUSDT": {},
    "ETHUSDT": {}
}

# DataFrame 列结构与数据库一致：
# columns: ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']
```

**设计要点：**
- 嵌套字典结构：`O(1)` 时间复杂度查找
- 使用 pandas DataFrame 便于数据操作和合并
- 列结构与数据库完全一致，便于转换
- 保留 48 小时数据，确保跨日无缝衔接

### 3. 时区处理规范

**核心原则：后端绝对 UTC，前端本地化**

**后端（Python + SQLite）：**
- 所有时间计算使用 `datetime.now(timezone.utc)`
- 数据库 `timestamp` 字段：Unix 毫秒时间戳（无时区概念）
- 数据库 `date` 字段：ISO 8601 格式必须带 `+00:00` 后缀
- 判断"今天"、"昨天"时，使用 UTC 时间

**前端（JavaScript）：**
- 接收 UTC 时间戳或 ISO 8601 字符串
- 由浏览器自动转换为用户本地时区（如 UTC+8）
- 图表库（TradingView、ECharts）自动处理时区显示

**示例：**
```python
# ✅ 正确：使用 UTC
today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

# ❌ 错误：使用本地时间
today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
```

### 4. 数据边界与跨日处理

**热缓存生命周期：**
- 热缓存保留最近 **48 小时**数据（滑动窗口）
- 不以 UTC 00:00 为界限强制清空
- 允许冷热数据重叠，确保无缝衔接

**数据边界定义：**
- **冷数据范围**：已成功下载并入库的历史数据
- **热数据范围**：最近 48 小时（包含昨天 + 今天）
- **重叠区域**：昨天的数据可能同时存在于冷层和热层

**跨日处理流程（关键：解决 Binance Vision 发布延迟）：**

1. **定时任务触发**（每天 UTC 08:00 或更晚）
2. **尝试下载**：从 Binance Vision 下载昨天的日线包
3. **成功入库后**：
   - 将昨天数据批量写入 SQLite
   - 从 `HOT_CACHE` 中删除 `< (今天 UTC 00:00)` 的数据
   - 记录成功日志
4. **下载失败时**：
   - **保留**热缓存中的昨天数据（关键！）
   - 记录警告日志
   - 下次定时任务重试
   - 系统继续正常服务（使用热缓存中的昨天数据）

**为什么需要 48 小时缓存？**

Binance Vision 的 T-1（昨天）日线数据包通常在今天的 UTC 04:00 到 08:00 才能下载。如果在 UTC 00:00 就清空昨天的热缓存，会导致数据断层。通过保留 48 小时数据，即使下载延迟，系统也能继续提供完整数据。

**查询聚合逻辑：**
```python
def get_kline_data(symbol: str, bar: str, start_date: str, end_date: str):
    # 1. 从 SQLite 查询冷数据
    cold_data = query_sqlite(symbol, bar, start_date, end_date)
    
    # 2. 从内存查询热数据
    hot_df = HOT_CACHE.get(symbol, {}).get(bar, pd.DataFrame())
    hot_data_filtered = hot_df[
        (hot_df['date'] >= start_date) & 
        (hot_df['date'] <= end_date)
    ]
    
    # 3. 合并去重（热数据优先）
    combined = pd.concat([
        pd.DataFrame(cold_data),
        hot_data_filtered
    ])
    combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
    combined = combined.sort_values('timestamp')
    
    return combined.to_dict('records')
```

**去重策略说明：**
- `keep='last'`：因为 `concat` 把热数据拼在后面，所以保留最后出现的值
- 效果：如果冷热数据都有同一时间戳，保留热数据（更新鲜）
- 实现了内存级别的 Upsert（更新插入）

## 核心组件设计

### 1. 后台离线数据管家（Batch Downloader）

**模块位置：** `app/services/batch_downloader.py`

**职责：**
- 每天定时下载 Binance Vision 历史数据
- 解析 CSV 并批量写入 SQLite
- 成功后清理热缓存中的过期数据

**核心函数：**

```python
async def daily_download_task():
    """每天定时执行的下载任务"""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        for interval in ["1m", "15m", "1h", "4h", "1d"]:
            try:
                # 1. 下载 Binance Vision ZIP
                success = await download_binance_daily(symbol, interval, yesterday)
                
                if success:
                    # 2. 清理热缓存中昨天的数据
                    cleanup_hot_cache(symbol, interval, yesterday)
                    logger.info(f"✓ Downloaded and cleaned: {symbol} {interval} {yesterday}")
                else:
                    # 3. 下载失败，保留热缓存
                    logger.warning(f"✗ Failed to download: {symbol} {interval} {yesterday}")
                    
            except Exception as e:
                logger.error(f"Error processing {symbol} {interval}: {e}")
                continue

async def download_binance_daily(symbol: str, interval: str, date: datetime.date) -> bool:
    """下载单个日线包"""
    # 构造 URL
    url = f"https://data.binance.vision/data/spot/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{date}.zip"
    
    # 下载 ZIP
    response = await httpx.get(url, timeout=30)
    if response.status_code == 404:
        return False  # 文件不存在
    
    # 解压并解析 CSV
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        csv_file = z.namelist()[0]
        df = pd.read_csv(z.open(csv_file), names=BINANCE_COLUMNS)
    
    # 转换时间戳和格式
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
    df['date'] = df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
    
    # 批量写入数据库
    records = df[['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']].to_dict('records')
    upsert_crypto_ohlc_batch(symbol, interval, records)
    
    return True

def cleanup_hot_cache(symbol: str, interval: str, date: datetime.date):
    """清理热缓存中指定日期之前的数据"""
    cutoff = datetime.combine(date, datetime.min.time()).replace(tzinfo=timezone.utc)
    
    if symbol in HOT_CACHE and interval in HOT_CACHE[symbol]:
        df = HOT_CACHE[symbol][interval]
        HOT_CACHE[symbol][interval] = df[df['timestamp'] >= cutoff]
```

**定时任务配置：**
- 使用 APScheduler 或 asyncio 实现
- 每天 UTC 08:00 执行
- 失败后每小时重试一次

### 2. 前台实时数据服务（Real-time Agent）

**模块位置：** `app/services/realtime_agent.py`

**职责：**
- 应用启动时预热热缓存（拉取今天的数据）
- 后台任务每 60 秒更新热缓存
- 提供数据查询接口

**核心函数：**

```python
async def warmup_hot_cache():
    """应用启动时预热热缓存"""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        for interval in ["1m", "15m", "1h", "4h", "1d"]:
            try:
                # 从 Binance API 拉取今天的所有数据
                data = await fetch_binance_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time=int(today_start.timestamp() * 1000),
                    limit=1500  # 足够覆盖一天的数据
                )
                
                # 初始化热缓存
                if symbol not in HOT_CACHE:
                    HOT_CACHE[symbol] = {}
                HOT_CACHE[symbol][interval] = pd.DataFrame(data)
                
                logger.info(f"✓ Warmed up: {symbol} {interval} ({len(data)} records)")
                
            except Exception as e:
                logger.error(f"Failed to warmup {symbol} {interval}: {e}")

async def update_hot_cache_loop():
    """后台循环更新热缓存"""
    while True:
        await asyncio.sleep(60)  # 每 60 秒
        
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            for interval in ["1m", "15m", "1h", "4h", "1d"]:
                try:
                    # 拉取最新的 10 根 K 线（确保不遗漏）
                    latest_data = await fetch_binance_klines(
                        symbol=symbol,
                        interval=interval,
                        limit=10
                    )
                    
                    # 追加到热缓存并去重
                    append_to_hot_cache(symbol, interval, latest_data)
                    
                except Exception as e:
                    logger.error(f"Failed to update {symbol} {interval}: {e}")

async def fetch_binance_klines(symbol: str, interval: str, start_time: int = None, limit: int = 10):
    """从 Binance REST API 获取 K 线数据"""
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    if start_time:
        params["startTime"] = start_time
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # 解析响应
        klines = response.json()
        return [
            {
                "timestamp": int(k[0]),
                "date": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat(),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5])
            }
            for k in klines
        ]

def append_to_hot_cache(symbol: str, interval: str, new_data: list):
    """追加新数据到热缓存并去重"""
    if symbol not in HOT_CACHE or interval not in HOT_CACHE[symbol]:
        HOT_CACHE[symbol][interval] = pd.DataFrame(new_data)
        return
    
    # 合并并去重
    existing_df = HOT_CACHE[symbol][interval]
    new_df = pd.DataFrame(new_data)
    combined = pd.concat([existing_df, new_df])
    combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
    combined = combined.sort_values('timestamp')
    
    # 限制缓存大小（最多 2880 条 = 48 小时 × 60 分钟）
    if len(combined) > 2880:
        combined = combined.tail(2880)
    
    HOT_CACHE[symbol][interval] = combined
```

**FastAPI 生命周期集成：**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    await warmup_hot_cache()
    update_task = asyncio.create_task(update_hot_cache_loop())
    
    yield
    
    # 关闭时
    update_task.cancel()

app = FastAPI(lifespan=lifespan)
```

### 3. API 聚合层

**模块位置：** `app/api/routes/crypto_klines.py`

**职责：**
- 接收前端查询请求
- 根据日期范围智能路由到冷/热层
- 合并去重后返回

**API 端点：**

```python
@router.get("/api/crypto/klines")
async def get_crypto_klines(
    symbol: str = Query(..., description="交易对，如 BTCUSDT"),
    interval: str = Query(..., description="时间间隔，如 1m, 15m, 1h, 4h, 1d"),
    start: str = Query(..., description="开始时间，ISO 格式"),
    end: str = Query(..., description="结束时间，ISO 格式")
):
    """获取加密货币 K 线数据（冷热数据自动合并）"""
    
    # 转换 symbol 格式（BTCUSDT -> BTC-USDT）
    db_symbol = f"{symbol[:3]}-{symbol[3:]}"
    
    # 映射 interval 到 bar 格式
    interval_map = {
        "1m": "1m",
        "15m": "15m",
        "1h": "1H",
        "4h": "4H",
        "1d": "1D"
    }
    bar = interval_map.get(interval)
    if not bar:
        raise HTTPException(status_code=400, detail=f"Invalid interval: {interval}")
    
    # 1. 查询冷数据（SQLite）
    cold_data = get_crypto_ohlc(db_symbol, bar, start, end)
    
    # 2. 查询热数据（内存）
    hot_df = HOT_CACHE.get(symbol, {}).get(interval, pd.DataFrame())
    if not hot_df.empty:
        hot_data_filtered = hot_df[
            (hot_df['date'] >= start) & 
            (hot_df['date'] <= end)
        ]
    else:
        hot_data_filtered = pd.DataFrame()
    
    # 3. 合并去重
    combined = pd.concat([
        pd.DataFrame(cold_data),
        hot_data_filtered
    ])
    
    if combined.empty:
        raise HTTPException(status_code=404, detail="No data found")
    
    combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
    combined = combined.sort_values('timestamp')
    
    # 4. 返回结果
    return {
        "symbol": symbol,
        "interval": interval,
        "data": combined[['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']].to_dict('records')
    }
```

## 错误处理与容灾

### 1. Binance API 调用失败

**场景：** 实时数据更新时 API 调用失败

**处理策略：**
- **重试机制**：3 次重试，指数退避（1s, 2s, 4s）
- **降级策略**：使用热缓存中的旧数据继续服务
- **告警机制**：超过 10 分钟无法更新时记录错误日志
- **用户体验**：前端继续显示缓存数据，不中断服务

**实现示例：**
```python
async def fetch_with_retry(url: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            response = await httpx.get(url, timeout=10)
            response.raise_for_status()
            return response
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # 指数退避
```

### 2. Binance Vision 下载失败

**场景：** 定时任务下载历史数据失败（404 或网络错误）

**处理策略：**
- **保留热缓存**：不清理昨天的数据，继续使用
- **重试策略**：每小时重试一次，直到成功
- **最大保留期**：热缓存最多保留 72 小时，超过后强制清理
- **告警机制**：连续失败 24 小时后发送告警

**实现示例：**
```python
async def download_with_retry():
    max_attempts = 24  # 24 小时
    for attempt in range(max_attempts):
        success = await download_binance_daily(...)
        if success:
            return True
        await asyncio.sleep(3600)  # 1 小时后重试
    
    # 24 小时后仍失败，强制清理
    logger.error("Failed to download after 24 hours, forcing cleanup")
    return False
```

### 3. 数据质量问题

**场景：** 接收到异常的 K 线数据（价格突变、成交量异常）

**检测规则：**
- 价格波动超过 50% 标记为可疑
- 成交量为 0 标记为可疑
- 时间戳乱序标记为可疑

**处理策略：**
- **仍然保存**：可疑数据写入数据库，不丢弃
- **添加标记**：在 API 响应中添加 `suspicious: true` 字段
- **人工审核**：定期检查可疑数据日志，必要时手动修正

**实现示例：**
```python
def detect_suspicious(df: pd.DataFrame) -> pd.DataFrame:
    df['suspicious'] = False
    
    # 检测价格突变
    df['price_change'] = df['close'].pct_change().abs()
    df.loc[df['price_change'] > 0.5, 'suspicious'] = True
    
    # 检测零成交量
    df.loc[df['volume'] == 0, 'suspicious'] = True
    
    return df
```

### 4. 内存溢出保护

**场景：** 热缓存无限增长导致内存溢出

**保护机制：**
- **大小限制**：单个 symbol+interval 最多保留 2880 条记录（48 小时 × 60 分钟）
- **自动清理**：超过限制时，删除最旧的数据
- **监控告警**：缓存总大小超过 100MB 时记录警告

**实现示例：**
```python
def limit_cache_size(df: pd.DataFrame, max_records: int = 2880) -> pd.DataFrame:
    if len(df) > max_records:
        return df.tail(max_records)
    return df

def get_cache_size() -> int:
    """计算热缓存总大小（字节）"""
    total_size = 0
    for symbol in HOT_CACHE:
        for interval in HOT_CACHE[symbol]:
            df = HOT_CACHE[symbol][interval]
            total_size += df.memory_usage(deep=True).sum()
    return total_size
```

### 5. 并发控制

**场景：** 多个请求同时修改热缓存

**保护机制：**
- **单进程部署**：确保 `workers=1`，避免多进程竞争
- **异步锁**：使用 `asyncio.Lock` 保护热缓存写操作
- **读写分离**：查询时复制 DataFrame，避免修改原始数据

**实现示例：**
```python
cache_lock = asyncio.Lock()

async def append_to_hot_cache_safe(symbol: str, interval: str, new_data: list):
    async with cache_lock:
        append_to_hot_cache(symbol, interval, new_data)
```

## 测试策略

### 1. 单元测试

**测试范围：**
- Binance API 数据解析正确性
- 冷热数据合并逻辑
- 时区转换正确性
- 去重逻辑（热数据优先）
- 缓存大小限制

**测试用例示例：**
```python
def test_merge_cold_hot_data():
    """测试冷热数据合并和去重"""
    cold_data = [
        {"timestamp": 1000, "close": 100.0},
        {"timestamp": 2000, "close": 101.0}
    ]
    hot_data = pd.DataFrame([
        {"timestamp": 2000, "close": 102.0},  # 重复，应保留热数据
        {"timestamp": 3000, "close": 103.0}
    ])
    
    result = merge_data(cold_data, hot_data)
    
    assert len(result) == 3
    assert result[result['timestamp'] == 2000]['close'].values[0] == 102.0  # 热数据优先

def test_timezone_handling():
    """测试时区处理正确性"""
    utc_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    timestamp_ms = int(utc_time.timestamp() * 1000)
    
    # 转换回来应该相等
    recovered = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    assert recovered == utc_time
```

### 2. 集成测试

**测试范围：**
- 完整的数据流：下载 → 存储 → 查询
- 跨日边界场景
- API 失败时的降级行为
- 定时任务执行

**测试用例示例：**
```python
@pytest.mark.asyncio
async def test_full_data_flow():
    """测试完整数据流"""
    # 1. 下载数据
    success = await download_binance_daily("BTCUSDT", "1h", date(2024, 1, 1))
    assert success
    
    # 2. 查询数据
    data = get_crypto_ohlc("BTC-USDT", "1H", "2024-01-01", "2024-01-02")
    assert len(data) > 0
    
    # 3. 验证数据完整性
    assert all(d['timestamp'] for d in data)
    assert all(d['close'] > 0 for d in data)

@pytest.mark.asyncio
async def test_cross_day_boundary():
    """测试跨日边界"""
    # 模拟跨日场景
    yesterday = date.today() - timedelta(days=1)
    today = date.today()
    
    # 查询跨越两天的数据
    data = get_crypto_ohlc("BTC-USDT", "1H", 
                           yesterday.isoformat(), 
                           today.isoformat())
    
    # 验证数据连续性
    timestamps = [d['timestamp'] for d in data]
    assert timestamps == sorted(timestamps)  # 时间戳有序
```

### 3. 压力测试

**测试范围：**
- 48 小时数据量的内存占用
- 并发查询性能
- 热缓存更新频率对系统的影响

**测试用例示例：**
```python
def test_memory_usage():
    """测试内存占用"""
    # 模拟 48 小时的 1 分钟数据
    records = 48 * 60  # 2880 条
    df = pd.DataFrame({
        'timestamp': range(records),
        'open': [100.0] * records,
        'high': [101.0] * records,
        'low': [99.0] * records,
        'close': [100.5] * records,
        'volume': [1000.0] * records
    })
    
    memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
    assert memory_mb < 10  # 单个 DataFrame 应小于 10MB

@pytest.mark.asyncio
async def test_concurrent_queries():
    """测试并发查询"""
    tasks = [
        get_crypto_klines("BTCUSDT", "1h", "2024-01-01", "2024-01-02")
        for _ in range(100)
    ]
    
    results = await asyncio.gather(*tasks)
    assert all(len(r['data']) > 0 for r in results)
```

### 4. 边界测试

**测试范围：**
- Binance Vision 文件不存在
- 网络超时
- 应用重启后的冷启动
- 跨年、跨月边界

**测试用例示例：**
```python
@pytest.mark.asyncio
async def test_file_not_found():
    """测试文件不存在的情况"""
    # 尝试下载不存在的日期
    success = await download_binance_daily("BTCUSDT", "1h", date(2099, 1, 1))
    assert not success  # 应该返回 False，不抛异常

@pytest.mark.asyncio
async def test_cold_start():
    """测试冷启动"""
    # 清空缓存
    HOT_CACHE.clear()
    
    # 执行预热
    await warmup_hot_cache()
    
    # 验证缓存已填充
    assert "BTCUSDT" in HOT_CACHE
    assert "1m" in HOT_CACHE["BTCUSDT"]
    assert len(HOT_CACHE["BTCUSDT"]["1m"]) > 0
```

## 部署注意事项

### 1. 单进程部署

**要求：** 必须使用单进程模式部署

**配置示例：**
```bash
# Uvicorn
uvicorn app.main:app --workers 1 --port 8000

# Gunicorn
gunicorn app.main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker
```

**原因：** 热缓存存储在进程内存中，多进程会导致数据不一致

### 2. 定时任务配置

**推荐方案：** 使用 APScheduler

**配置示例：**
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(
    daily_download_task,
    trigger='cron',
    hour=8,
    minute=0,
    timezone='UTC'
)
scheduler.start()
```

### 3. 监控指标

**关键指标：**
- 热缓存大小（MB）
- 热缓存更新延迟（秒）
- API 查询响应时间（ms）
- 定时任务成功率（%）
- Binance API 调用失败次数

**日志示例：**
```python
logger.info(f"Hot cache size: {get_cache_size() / 1024 / 1024:.2f} MB")
logger.info(f"Last update: {last_update_time}")
logger.info(f"API response time: {response_time_ms} ms")
```

## 总结

本设计实现了一个轻量级、高可靠的加密货币 K 线数据冷热分离架构：

**核心优势：**
1. **数据准确性**：历史数据来自 Binance 官方归档，绝对可信
2. **实时性**：当天数据 60 秒更新，满足实时查看需求
3. **容灾能力**：优雅降级，下载失败不影响服务
4. **简单可靠**：单机部署，无外部依赖，易于维护
5. **时区安全**：严格 UTC 时间处理，避免跨时区问题

**适用场景：**
- 个人量化交易系统
- 小型金融数据平台
- 加密货币行情展示应用

**扩展方向：**
- 支持更多交易对
- 添加 WebSocket 实时推送
- 升级到 Redis 支持分布式部署
