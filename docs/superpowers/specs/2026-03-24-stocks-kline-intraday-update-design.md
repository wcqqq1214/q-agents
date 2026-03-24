# Stocks K-Line 盘中增量更新架构设计

**日期：** 2026-03-24  
**状态：** 已批准  
**方案：** 轻量级盘中更新（方案 A）

## 概述

为 Stocks K-Line 添加盘中增量更新能力，解决当前数据断更问题（数据停留在 2026-03-19，缺失 3/20 和 3/23 两个交易日），并支持盘中查看未闭合的当日 K 线。

采用轻量级架构，通过 15 分钟轮询 + 5 天数据回溯实现自动 Gap 修复，无需引入内存热缓存，保持系统简单可靠。

## 设计目标

✅ **解决数据断更**：自动修复历史 Gap（如 3/20-3/23）  
✅ **盘中实时更新**：支持查看未闭合的当日 K 线  
✅ **架构轻量化**：无需内存热缓存，保持 SQLite 单层存储  
✅ **API 成本可控**：仅在交易时段更新，每天约 26 次调用  
✅ **非阻塞执行**：不影响 FastAPI 正常 API 响应  
✅ **时区安全**：严格 UTC 转换，避免跨时区问题  

## 问题背景

### 当前问题

1. **数据断更**：今天是 2026-03-24（周二），但数据只到 2026-03-19（上周四）
   - 缺失：3/20（周五）和 3/23（周一）两个交易日
   - 原因：APScheduler 定时任务可能在周末前挂掉或 API 超时

2. **无盘中更新**：当前架构只支持每日定时更新，无法在盘中看到当天的最新价格

3. **无自愈能力**：一旦某天更新失败，Gap 会永久存在，需要手动修复

### 为什么不完全对齐 Crypto 架构？

**Crypto 架构特点：**
- 24/7 永不休市，60 秒高频轮询
- Lambda 架构：内存热缓存（48 小时）+ SQLite 冷存储
- 复杂的冷热数据合并与去重逻辑

**Stocks 市场特点：**
- 严格的交易时间（美东 09:30-16:00）
- 周末双休 + 法定节假日
- 日线数据为主，无需秒级更新

**结论：** 对于日线数据，60 秒轮询和 Lambda 架构属于过度设计，会浪费 API 配额并增加系统复杂度。


## 整体架构

### 架构图

```
APScheduler (15分钟轮询: :01, :16, :31, :46)
    ↓
交易时段守门员 (美东 09:31-16:05)
    ↓ (通过)
yfinance 批量拉取 (最近5天 1d 数据)
    ↓
时区标准化 (美东 → UTC)
    ↓
SQLite Upsert (ON CONFLICT DO UPDATE)
    ↓
前端查询 (读取最新数据)
```

### 核心组件

**1. 交易时段守门员（Trading Hours Gatekeeper）**
- **职责**：判断是否应该执行更新
- **检查项**：
  - 是否为交易日（排除周末和美国节假日）
  - 当前美东时间是否在 09:31-16:05 之间
- **实现**：`app/services/trading_hours.py`
- **依赖**：`pandas-market-calendars` 用于精确节假日检测

**2. 数据拉取与清洗模块**
- **职责**：从 yfinance 批量拉取数据并标准化
- **关键参数**：`period='5d', interval='1d'`（拉取最近 5 天）
- **时区处理**：
  - yfinance 返回的 naive datetime 是美东午夜
  - 先 `tz_localize('America/New_York')`
  - 再 `tz_convert('UTC')`
  - 最后 `tz_localize(None)` 移除时区信息
- **实现**：`app/services/stock_updater.py`

**3. Upsert 逻辑（覆盖策略）**
- **职责**：插入新数据或覆盖已有数据
- **SQL 策略**：
  ```sql
  INSERT INTO ohlc (symbol, date, open, high, low, close, volume)
  VALUES (?, ?, ?, ?, ?, ?, ?)
  ON CONFLICT(symbol, date) DO UPDATE SET
      open = excluded.open,
      high = excluded.high,
      low = excluded.low,
      close = excluded.close,
      volume = excluded.volume
  ```
- **用途**：支持盘中多次更新同一天的未闭合 K 线

**4. APScheduler 调度器**
- **触发时间**：每小时的 1, 16, 31, 46 分（美东时间）
- **时区配置**：`timezone='America/New_York'`（自动处理夏令时）
- **防重叠**：`max_instances=1`
- **异步包装**：使用 `asyncio.to_thread()` 避免阻塞事件循环

### 数据流向

**场景 1：盘中更新（09:31-16:05）**
```
09:46 ET → 守门员通过 → 拉取 5 天数据 → Upsert 覆盖今天的 K 线 → 前端看到最新价格
10:01 ET → 守门员通过 → 拉取 5 天数据 → Upsert 覆盖今天的 K 线 → 前端看到更新价格
...
16:01 ET → 守门员通过 → 拉取 5 天数据 → Upsert 固化今天的收盘 K 线
```

**场景 2：盘外时段（16:05-09:31 或周末）**
```
16:16 ET → 守门员拒绝 → 跳过更新
20:01 ET → 守门员拒绝 → 跳过更新
周六 10:01 ET → 守门员拒绝 → 跳过更新
```

**场景 3：自动 Gap 修复**
```
假设 3/20 更新失败，数据停留在 3/19
3/23 10:01 ET → 拉取最近 5 天（3/19-3/23）→ Upsert 自动填补 3/20 和 3/23 → Gap 修复
```

### 与 Crypto 架构对比

| 特性 | Crypto K-line | Stocks K-line (方案 A) |
|------|---------------|------------------------|
| **数据源** | Binance API | yfinance |
| **市场特性** | 24/7 永不休市 | 美东 09:30-16:00 + 节假日 |
| **更新频率** | 60 秒 | 15 分钟（仅交易时段） |
| **热缓存** | ✅ 内存 48 小时 | ❌ 不需要 |
| **冷存储** | ✅ SQLite | ✅ SQLite |
| **架构模式** | Lambda（冷热分离） | 单层 Upsert |
| **自愈能力** | ✅ 48 小时重叠 | ✅ 5 天回溯 |
| **复杂度** | 高 | 低 |
| **API 调用/天** | ~1440 次 | ~26 次 |


## 核心实现细节

### 1. 交易时段守门员

**文件位置：** `app/services/trading_hours.py`

**核心函数：**

```python
def should_update_stocks() -> bool:
    """
    主守门员函数：决定是否应该更新股票数据。
    
    检查逻辑：
    1. 是否为美国市场节假日
    2. 是否在交易时段（美东 09:31-16:05）
    
    Returns:
        True 表示应该更新，False 表示跳过
    """
    # 检查节假日
    if is_us_holiday():
        return False
    
    # 检查交易时段
    if not is_trading_hours():
        return False
    
    return True
```

**时区处理：**
```python
from zoneinfo import ZoneInfo

US_EASTERN = ZoneInfo("America/New_York")
now_et = datetime.now(US_EASTERN)  # 自动处理 EDT/EST
```

**节假日检测：**
```python
import pandas_market_calendars as mcal

nyse = mcal.get_calendar('NYSE')
schedule = nyse.valid_days(start_date=today, end_date=today)
is_holiday = len(schedule) == 0
```

**时间窗口设计：**
- 开盘缓冲：09:31（而非 09:30）
- 收盘缓冲：16:05（而非 16:00）
- 原因：确保能捕获最后一根收盘 K 线

### 2. 数据拉取与时区标准化

**文件位置：** `app/services/stock_updater.py`

**批量拉取：**
```python
data = yf.download(
    tickers=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA'],
    period='5d',        # 拉取最近 5 天
    interval='1d',      # 日线数据
    group_by='ticker',  # 按股票分组
    auto_adjust=True,   # 使用复权价格
    progress=False      # 禁用进度条
)
```

**时区标准化（关键！）：**
```python
def normalize_timezone(df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化时区到 UTC。
    
    处理 yfinance 的时区坑：
    - yfinance 返回的日线数据是美东午夜
    - 有时带时区（America/New_York），有时不带（naive）
    - 我们需要统一转换为 UTC
    """
    US_EASTERN = ZoneInfo("America/New_York")
    UTC = ZoneInfo("UTC")
    
    if df.index.tz is None:
        # Naive datetime，假设为美东午夜
        df.index = df.index.tz_localize(US_EASTERN).tz_convert(UTC)
    else:
        # 已有时区，直接转换
        df.index = df.index.tz_convert(UTC)
    
    # 移除时区信息（数据库存储为 TEXT）
    df.index = df.index.tz_localize(None)
    
    return df
```

**为什么拉取 5 天而不是 1 天？**
1. **自动修复 Gap**：如果某天更新失败，下次会自动补上
2. **应对数据修正**：上游可能在盘后修正昨天的价格
3. **处理除权除息**：前复权调整会影响近期价格

### 3. Upsert 逻辑（覆盖策略）

**关键改进：从 DO NOTHING 改为 DO UPDATE**

```python
def upsert_ohlc_overwrite(symbol: str, data: List[Dict]):
    """
    插入或覆盖 OHLC 数据。
    
    使用 ON CONFLICT DO UPDATE 而非 DO NOTHING，
    以支持盘中多次更新同一天的未闭合 K 线。
    """
    conn.executemany("""
        INSERT INTO ohlc (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, date) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume
    """, [(symbol.upper(), d['date'], d['open'], d['high'], 
           d['low'], d['close'], d['volume']) for d in data])
```

**Upsert 行为示例：**
```
10:01 ET → 插入 2026-03-24: Open=100, High=102, Low=99, Close=101
10:16 ET → 更新 2026-03-24: Open=100, High=103, Low=99, Close=102
10:31 ET → 更新 2026-03-24: Open=100, High=103, Low=98, Close=101
...
16:01 ET → 更新 2026-03-24: Open=100, High=105, Low=98, Close=104 (收盘固化)
```

### 4. 异步包装器（防止阻塞事件循环）

**问题：** yfinance 和 SQLite 都是同步阻塞 I/O，会阻塞 FastAPI 事件循环

**解决方案：** 使用 `asyncio.to_thread()` 在线程池中执行

```python
def update_stocks_intraday_sync():
    """同步版本：包含阻塞 I/O"""
    if not should_update_stocks():
        return
    
    data_by_symbol = fetch_recent_ohlc(SYMBOLS, days=5)
    
    for symbol, records in data_by_symbol.items():
        upsert_ohlc_overwrite(symbol, records)
        update_metadata(symbol, ...)

async def update_stocks_intraday():
    """异步包装器：在线程池中执行"""
    try:
        await asyncio.to_thread(update_stocks_intraday_sync)
    except Exception as e:
        logger.error(f"Update failed: {e}", exc_info=True)
```

**APScheduler 配置：**
```python
scheduler.add_job(
    update_stocks_intraday,  # 直接调用 async 函数
    trigger=CronTrigger(
        minute='1,16,31,46',
        timezone='America/New_York'
    ),
    max_instances=1  # 防止重叠执行
)
```


## 关键设计决策

### 为什么选择 15 分钟轮询？

**考虑因素：**
1. **数据粒度**：日线数据，无需秒级更新
2. **API 成本**：yfinance 免费但有速率限制
3. **用户体验**：15 分钟延迟对日线交易者完全可接受
4. **系统负载**：每天仅 26 次调用，极低开销

**对比其他频率：**
- **1 分钟**：过度频繁，浪费 API 配额（每天 ~390 次）
- **5 分钟**：稍好，但仍然偏高（每天 ~78 次）
- **15 分钟**：✅ 甜点位（每天 ~26 次）
- **30 分钟**：太慢，盘中只更新 13 次
- **60 分钟**：太慢，盘中只更新 7 次

### 为什么时间偏移到 :01/:16/:31/:46？

**问题：** 如果在正点（:00/:15/:30/:45）拉取，上游 API 可能还没生成刚闭合的 K 线

**解决方案：** 向后偏移 1 分钟

**示例：**
```
09:45:00 → K 线闭合（09:30-09:45）
09:45:00 → 如果此时拉取，可能拿不到这根 K 线
09:46:00 → 偏移后拉取，确保能拿到 09:45 的 K 线 ✅
```

**收盘 K 线保障：**
```
16:00:00 → 收盘 K 线闭合（15:45-16:00）
16:01:00 → 守门员窗口延长到 16:05，确保能捕获收盘 K 线 ✅
```

### 为什么拉取 5 天而不是 1 天？

**核心价值：自愈能力**

**场景 1：网络故障导致断更**
```
3/20 10:01 → 网络超时，更新失败
3/20 10:16 → 网络超时，更新失败
...
3/23 10:01 → 网络恢复，拉取 5 天（3/19-3/23）→ 自动填补 3/20 Gap ✅
```

**场景 2：上游数据修正**
```
3/23 16:01 → 拉取收盘价 $100.00
3/24 10:01 → 拉取 5 天，发现 3/23 修正为 $100.50 → 自动覆盖 ✅
```

**场景 3：除权除息**
```
3/24 → AAPL 除息，前复权价格调整
3/24 10:01 → 拉取 5 天，近期价格全部更新 → 保持数据一致性 ✅
```

**成本分析：**
- 拉取 1 天：7 只股票 × 1 天 = 7 条记录
- 拉取 5 天：7 只股票 × 5 天 = 35 条记录
- 增加：28 条记录（可忽略不计）

## 日志输出

### 正常更新日志

```
2026-03-24 10:01:00 INFO ============================================================
2026-03-24 10:01:00 INFO Starting intraday stock update
2026-03-24 10:01:00 INFO ============================================================
2026-03-24 10:01:00 INFO ✓ Gatekeeper passed: proceeding with stock update
2026-03-24 10:01:01 INFO Fetching 5-day data for 7 symbols...
2026-03-24 10:01:03 INFO ✓ AAPL: 5 records | Latest: 2026-03-24 Close=$175.23
2026-03-24 10:01:03 INFO ✓ MSFT: 5 records | Latest: 2026-03-24 Close=$420.15
2026-03-24 10:01:03 INFO ✓ GOOGL: 5 records | Latest: 2026-03-24 Close=$142.89
2026-03-24 10:01:03 INFO ✓ AMZN: 5 records | Latest: 2026-03-24 Close=$178.45
2026-03-24 10:01:03 INFO ✓ NVDA: 5 records | Latest: 2026-03-24 Close=$875.60
2026-03-24 10:01:03 INFO ✓ META: 5 records | Latest: 2026-03-24 Close=$485.20
2026-03-24 10:01:03 INFO ✓ TSLA: 5 records | Latest: 2026-03-24 Close=$195.30
2026-03-24 10:01:05 INFO ============================================================
2026-03-24 10:01:05 INFO Update complete: 7/7 symbols updated
2026-03-24 10:01:05 INFO Latest prices: AAPL=$175.23 | MSFT=$420.15 | GOOGL=$142.89 | AMZN=$178.45 | NVDA=$875.60 | META=$485.20 | TSLA=$195.30
2026-03-24 10:01:05 INFO ============================================================
```

### 守门员拒绝日志

```
2026-03-24 16:16:00 INFO Skipping update: outside trading hours
2026-03-24 20:01:00 INFO Skipping update: outside trading hours
2026-03-25 10:01:00 INFO Skipping update: US market holiday (Christmas)
```

### 错误日志

```
2026-03-24 10:01:03 ERROR Failed to process TSLA: HTTPError 429 (Rate Limit)
2026-03-24 10:01:05 INFO Update complete: 6/7 symbols updated
```

## 监控与调试

### 调度器状态端点（可选）

```python
@app.get("/api/scheduler/status")
async def get_scheduler_status():
    """获取 APScheduler 状态和下次运行时间"""
    jobs = scheduler.get_jobs()
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat(),
                "trigger": str(job.trigger)
            }
            for job in jobs
        ]
    }
```

### 手动触发端点（可选）

```python
@app.post("/api/scheduler/trigger")
async def trigger_update():
    """手动触发更新（用于测试）"""
    await update_stocks_intraday()
    return {"status": "triggered"}
```

### 关键监控指标

- **更新成功率**：成功更新的股票数 / 总股票数
- **API 响应时间**：yfinance 调用耗时
- **数据新鲜度**：最新数据的时间戳
- **守门员拒绝次数**：盘外时段的跳过次数


## 文件结构

```
finance-agent/
├── app/
│   ├── api/
│   │   └── main.py                    # ✏️ 修改：添加 APScheduler
│   ├── database/
│   │   ├── ohlc.py                    # ✅ 已存在（无需修改）
│   │   └── schema.py                  # ✅ 已存在
│   └── services/
│       ├── trading_hours.py           # 🆕 新建：交易时段守门员
│       └── stock_updater.py           # 🆕 新建：数据拉取与更新
├── scripts/
│   └── backfill_stock_gap.py          # 🆕 新建：一次性补数据
└── pyproject.toml                     # ✏️ 修改：添加依赖
```

## 依赖管理

### 新增依赖

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "yfinance>=0.2.40",                # Yahoo Finance API
    "apscheduler>=3.10.4",             # 任务调度
    "pandas-market-calendars>=4.3.3",  # 美国节假日检测
]
```

### 安装命令

```bash
cd /home/wcqqq21/finance-agent
uv pip install yfinance apscheduler pandas-market-calendars
```

## 实施步骤

### 步骤 1：安装依赖

```bash
uv pip install yfinance apscheduler pandas-market-calendars
```

### 步骤 2：创建交易时段守门员

创建文件：`app/services/trading_hours.py`

核心函数：
- `is_trading_hours()` - 检查是否在交易时段
- `is_us_holiday()` - 检查是否为节假日
- `should_update_stocks()` - 主守门员函数

### 步骤 3：创建数据更新模块

创建文件：`app/services/stock_updater.py`

核心函数：
- `fetch_recent_ohlc()` - 批量拉取数据
- `normalize_timezone()` - 时区标准化
- `upsert_ohlc_overwrite()` - Upsert 覆盖逻辑
- `update_stocks_intraday_sync()` - 同步更新函数
- `update_stocks_intraday()` - 异步包装器

### 步骤 4：修改 FastAPI 主文件

修改文件：`app/api/main.py`

添加内容：
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.stock_updater import update_stocks_intraday

scheduler = AsyncIOScheduler(timezone="America/New_York")

@app.on_event("startup")
async def startup_event():
    scheduler.add_job(
        update_stocks_intraday,
        trigger=CronTrigger(minute='1,16,31,46', timezone='America/New_York'),
        id='intraday_stock_update',
        max_instances=1
    )
    scheduler.start()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown(wait=True)
```

### 步骤 5：运行补数据脚本

创建文件：`scripts/backfill_stock_gap.py`

```python
"""一次性补数据脚本，修复 2026-03-20 到 2026-03-23 的 Gap"""

from app.services.stock_updater import fetch_recent_ohlc, upsert_ohlc_overwrite

# 拉取最近 10 天数据
data_by_symbol = fetch_recent_ohlc(SYMBOLS, days=10)

# Upsert 到数据库
for symbol, records in data_by_symbol.items():
    upsert_ohlc_overwrite(symbol, records)
```

运行：
```bash
uv run python scripts/backfill_stock_gap.py
```

### 步骤 6：验证数据完整性

```bash
uv run python -c "
from app.database.ohlc import get_ohlc
for symbol in ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']:
    records = get_ohlc(symbol, '2026-03-20', '2026-03-23')
    print(f'{symbol}: {len(records)} records')
"
```

预期输出：
```
AAPL: 2 records
MSFT: 2 records
GOOGL: 2 records
AMZN: 2 records
NVDA: 2 records
META: 2 records
TSLA: 2 records
```

### 步骤 7：重启应用

```bash
uv run uvicorn app.api.main:app --port 8080
```

查看日志，确认调度器启动：
```
INFO ✓ APScheduler started: updates at :01, :16, :31, :46 (ET)
```

### 步骤 8：监控首次更新

等待下一个触发时间（如 10:01 ET），查看日志：
```
INFO Starting intraday stock update
INFO ✓ AAPL: 5 records | Latest: 2026-03-24 Close=$175.23
...
INFO Update complete: 7/7 symbols updated
```

## 一次性补数据脚本

**完整代码：** `scripts/backfill_stock_gap.py`

```python
"""
一次性补数据脚本，修复 2026-03-20 到 2026-03-23 的数据 Gap。

Usage:
    uv run python scripts/backfill_stock_gap.py
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.stock_updater import (
    fetch_recent_ohlc, 
    upsert_ohlc_overwrite, 
    update_metadata
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']

def main():
    logger.info("=" * 70)
    logger.info("开始补数据：2026-03-20 到 2026-03-23")
    logger.info("=" * 70)
    
    # 拉取最近 10 天数据（确保覆盖 Gap）
    data_by_symbol = fetch_recent_ohlc(SYMBOLS, days=10)
    
    if not data_by_symbol:
        logger.error("❌ 未获取到数据，终止补数据")
        return 1
    
    # Upsert 每只股票
    success_count = 0
    for symbol, records in data_by_symbol.items():
        try:
            if records:
                upsert_ohlc_overwrite(symbol, records)
                dates = [r['date'] for r in records]
                update_metadata(symbol, min(dates), max(dates))
                success_count += 1
                logger.info(f"✓ {symbol}: {len(records)} 条记录已补充")
        except Exception as e:
            logger.error(f"❌ {symbol} 补数据失败: {e}")
    
    logger.info("=" * 70)
    logger.info(f"补数据完成: {success_count}/{len(SYMBOLS)} 只股票")
    logger.info("=" * 70)
    
    # 验证 Gap 已填补
    logger.info("\n验证 Gap 是否已填补...")
    from app.database.ohlc import get_ohlc
    
    for symbol in SYMBOLS:
        records = get_ohlc(symbol, '2026-03-20', '2026-03-23')
        logger.info(f"{symbol}: {len(records)} 条记录在 Gap 期间")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
```


## 成功标准

✅ **数据完整性**
- 历史 Gap（3/20, 3/23）已修复
- 所有 7 只股票数据完整

✅ **盘中更新**
- 交易时段每 15 分钟更新一次
- 能看到未闭合的当日 K 线

✅ **守门员正常工作**
- 盘外时段自动跳过更新
- 节假日自动跳过更新

✅ **非阻塞执行**
- FastAPI API 响应时间不受影响
- 更新任务在后台线程执行

✅ **日志清晰**
- 每次更新显示最新收盘价
- 错误日志包含完整堆栈信息

✅ **自愈能力**
- 单次更新失败不影响后续更新
- 自动修复历史 Gap

## 错误处理策略

### 1. 网络错误

**场景：** yfinance API 调用超时或失败

**处理：**
- 单个股票失败不影响其他股票
- 记录错误日志
- 下次更新时自动重试（5 天回溯）

### 2. 数据质量问题

**场景：** 返回的数据包含 NaN 或异常值

**处理：**
- 跳过包含 NaN 的记录
- 记录警告日志
- 不写入数据库

### 3. 数据库错误

**场景：** SQLite 写入失败

**处理：**
- 捕获异常并记录
- 不影响其他股票的更新
- 下次更新时重试

### 4. 调度器错误

**场景：** APScheduler 任务执行失败

**处理：**
- 异常被 `try-except` 捕获
- 记录完整堆栈信息
- 不影响下次调度

## 未来扩展方向

### 1. 支持更多股票

当前仅支持 Magnificent Seven，未来可扩展到：
- S&P 500 成分股
- 用户自定义股票列表

### 2. 支持分钟级数据

如果需要更精细的数据粒度：
- 添加 15 分钟 K 线支持
- 添加 1 小时 K 线支持
- 需要引入内存热缓存

### 3. WebSocket 实时推送

如果需要真正的实时更新：
- 前端通过 WebSocket 连接
- 后端推送最新价格变化
- 无需前端轮询

### 4. 数据质量监控

添加数据质量检查：
- 价格异常波动检测
- 成交量异常检测
- 数据完整性报告

## 设计总结

### 核心优势

✅ **轻量级架构**：无需 Redis 或内存热缓存，保持系统简单  
✅ **自愈能力强**：5 天回溯自动修复历史 Gap  
✅ **API 成本低**：每天仅 26 次调用，远低于 Crypto 的 1440 次  
✅ **时区安全**：严格的 UTC 转换，避免跨时区问题  
✅ **非阻塞执行**：异步包装，不影响 FastAPI 性能  
✅ **智能守门**：只在交易时段更新，节省资源  

### 关键技术决策

| 决策 | 理由 |
|------|------|
| 15 分钟轮询 | 平衡实时性与 API 成本 |
| 拉取 5 天数据 | 自动修复 Gap + 应对数据修正 |
| Upsert 覆盖策略 | 支持盘中未闭合 K 线更新 |
| 时间偏移（:01/:16/:31/:46） | 避开 API 延迟，确保数据完整 |
| 异步包装 | 不阻塞 FastAPI 事件循环 |
| 美东时区调度 | 自动处理夏令时，与市场时间对齐 |

### 与 Crypto 架构的差异

Stocks 架构更简单，因为：
- 股票市场有明确的交易时间
- 日线数据无需秒级更新
- 无需复杂的冷热数据合并

但保留了核心优势：
- 自愈能力（通过 5 天回溯）
- 数据一致性（通过 Upsert 覆盖）
- 系统可靠性（通过错误隔离）

---

**实施完成后，Stocks K-Line 将具备与 Crypto K-Line 相当的数据完整性和实时性，同时保持更低的系统复杂度和 API 成本。**


---

## 附录：实施前的关键检查清单

### Critical 问题（必须修复）

#### 1. 统一调度器类型 ⚠️

**当前状态：** `app/api/main.py:26` 使用 `BackgroundScheduler`

**需要改为：**
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="America/New_York")
```

**影响：** 混用调度器类型可能导致异步任务执行问题

#### 2. 添加 upsert_ohlc_overwrite 函数 ⚠️

**当前状态：** `app/database/ohlc.py:145-149` 使用 `ON CONFLICT DO NOTHING`

**需要添加：** 新函数 `upsert_ohlc_overwrite` 使用 `ON CONFLICT DO UPDATE`

**影响：** 盘中多次更新同一天的 K 线时，只有第一次会写入

#### 3. 添加 pandas-market-calendars 依赖 ⚠️

**需要执行：**
```bash
uv pip install pandas-market-calendars
```

**需要添加到 pyproject.toml：**
```toml
"pandas-market-calendars>=4.3.3",
```

**影响：** 无法进行美国节假日检测，守门员功能无法正常工作

### 表结构依赖确认

**必须确认 ohlc 表有 UNIQUE 约束：**
```sql
CREATE TABLE IF NOT EXISTS ohlc (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    PRIMARY KEY (symbol, date)  -- 必须有此约束
);
```

**验证命令：**
```bash
uv run python -c "
from app.database.schema import get_conn
conn = get_conn()
result = conn.execute(\"SELECT sql FROM sqlite_master WHERE type='table' AND name='ohlc'\").fetchone()
print(result[0] if result else 'Table not found')
"
```

