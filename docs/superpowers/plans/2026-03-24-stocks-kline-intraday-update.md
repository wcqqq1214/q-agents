# Stocks K-Line 盘中增量更新实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Stocks K-Line 添加盘中增量更新能力，解决数据断更问题并支持查看未闭合的当日 K 线

**Architecture:** 轻量级架构，通过 APScheduler 每 15 分钟轮询 yfinance API，使用交易时段守门员控制更新时机，通过 5 天数据回溯实现自动 Gap 修复，使用 Upsert 覆盖策略支持盘中更新

**Tech Stack:** FastAPI, APScheduler, yfinance, pandas-market-calendars, SQLite, asyncio

**Spec Document:** `docs/superpowers/specs/2026-03-24-stocks-kline-intraday-update-design.md`

---

## File Structure

**New Files:**
- `app/services/trading_hours.py` - 交易时段守门员（判断是否应该更新）
- `app/services/stock_updater.py` - 数据拉取与更新逻辑
- `scripts/backfill_stock_gap.py` - 一次性补数据脚本

**Modified Files:**
- `app/api/main.py` - 集成 APScheduler 调度器
- `pyproject.toml` - 添加新依赖

**No Changes:**
- `app/database/ohlc.py` - 已有 upsert_ohlc 函数，但需要新增 upsert_ohlc_overwrite
- `app/database/schema.py` - 表结构已满足需求

---

## Task 1: 安装依赖并验证环境

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加 pandas-market-calendars 依赖**

在 `pyproject.toml` 的 `dependencies` 数组中添加：

```toml
"pandas-market-calendars>=4.3.3",
```

注意：`yfinance` 和 `apscheduler` 已存在，无需添加。

- [ ] **Step 2: 同步依赖**

Run: `uv sync`
Expected: Successfully installed pandas-market-calendars

- [ ] **Step 3: 验证依赖安装**

Run: `uv run python -c "import pandas_market_calendars as mcal; print(mcal.__version__)"`
Expected: 输出版本号（如 4.3.3 或更高）

- [ ] **Step 4: 验证表结构**

Run: `uv run python -c "from app.database.schema import get_conn; conn = get_conn(); result = conn.execute('SELECT sql FROM sqlite_master WHERE type=\"table\" AND name=\"ohlc\"').fetchone(); print(result[0] if result else 'Table not found')"`
Expected: 输出包含 `PRIMARY KEY (symbol, date)` 的 CREATE TABLE 语句

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add pandas-market-calendars for US holiday detection"
```

---

## Task 2: 创建交易时段守门员模块

**Files:**
- Create: `app/services/trading_hours.py`

- [ ] **Step 0: 创建 services 目录（如果不存在）**

Run: `mkdir -p /home/wcqqq21/finance-agent/app/services`
Expected: 目录创建成功（如果已存在则无操作）

- [ ] **Step 1: 创建文件并添加基础结构**

创建 `app/services/trading_hours.py`，添加以下代码：

```python
"""Trading hours gatekeeper for US stock market."""
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# US Eastern timezone
US_EASTERN = ZoneInfo("America/New_York")

# Trading hours (US Eastern Time)
MARKET_OPEN = time(9, 31)   # 09:31 ET (留1分钟缓冲)
MARKET_CLOSE = time(16, 5)  # 16:05 ET (留5分钟缓冲)
```

- [ ] **Step 2: 实现交易时段检查函数**

在同一文件中添加：

```python
def is_trading_hours() -> bool:
    """
    Check if current time is within US stock market trading hours.

    Returns:
        True if market is open and within trading hours, False otherwise
    """
    # Get current time in US Eastern timezone
    now_et = datetime.now(US_EASTERN)

    # Check if weekend
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        logger.debug(f"Weekend detected: {now_et.strftime('%A')}")
        return False

    # Check if within trading hours
    current_time = now_et.time()
    if MARKET_OPEN <= current_time <= MARKET_CLOSE:
        logger.debug(f"Within trading hours: {current_time}")
        return True
    else:
        logger.debug(f"Outside trading hours: {current_time}")
        return False
```

- [ ] **Step 3: 实现节假日检查函数**

在同一文件中添加：

```python
def is_us_holiday() -> bool:
    """
    Check if today is a US market holiday.

    Uses pandas_market_calendars for accurate holiday detection.
    Falls back to basic weekend check if library not available.

    Returns:
        True if today is a holiday, False otherwise
    """
    try:
        import pandas_market_calendars as mcal

        # Get NYSE calendar
        nyse = mcal.get_calendar('NYSE')

        # Get current date in US Eastern timezone
        now_et = datetime.now(US_EASTERN)
        today = now_et.date()

        # Check if today is a valid trading day
        schedule = nyse.valid_days(start_date=today, end_date=today)

        is_holiday = len(schedule) == 0
        if is_holiday:
            logger.info(f"US market holiday detected: {today}")

        return is_holiday

    except ImportError:
        logger.warning("pandas_market_calendars not installed, using basic weekend check")
        now_et = datetime.now(US_EASTERN)
        return now_et.weekday() >= 5
```

- [ ] **Step 4: 实现主守门员函数**

在同一文件中添加：

```python
def should_update_stocks() -> bool:
    """
    Main gatekeeper function: decide if stock data should be updated now.

    Returns:
        True if update should proceed, False otherwise
    """
    # Check holiday first (cheaper check)
    if is_us_holiday():
        logger.info("Skipping update: US market holiday")
        return False

    # Check trading hours
    if not is_trading_hours():
        logger.info("Skipping update: outside trading hours")
        return False

    logger.info("✓ Gatekeeper passed: proceeding with stock update")
    return True
```

- [ ] **Step 5: 测试守门员函数**

Run: `uv run python -c "from app.services.trading_hours import should_update_stocks; result = should_update_stocks(); print(f'Should update: {result}')"`
Expected: 根据当前时间输出 True 或 False，并显示相应的日志

- [ ] **Step 6: Commit**

```bash
git add app/services/trading_hours.py
git commit -m "feat: add trading hours gatekeeper for US stock market

- Check if current time is within trading hours (09:31-16:05 ET)
- Check if today is a US market holiday using NYSE calendar
- Fallback to basic weekend check if pandas_market_calendars unavailable"
```

---

## Task 3: 创建数据更新模块（第1部分：基础函数）

**Files:**
- Create: `app/services/stock_updater.py`

- [ ] **Step 1: 创建文件并添加导入和常量**

创建 `app/services/stock_updater.py`，添加以下代码：

```python
"""Stock data updater with intraday support."""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
from zoneinfo import ZoneInfo

import yfinance as yf
import pandas as pd

from app.database.ohlc import update_metadata
from app.services.trading_hours import should_update_stocks

logger = logging.getLogger(__name__)

# Magnificent Seven stocks
SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']

# Timezones
UTC = ZoneInfo("UTC")
US_EASTERN = ZoneInfo("America/New_York")
```

- [ ] **Step 2: 实现时区标准化函数**

在同一文件中添加：

```python
def normalize_timezone(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize DataFrame index timezone to UTC.

    Handles the yfinance timezone quirks:
    - yfinance returns daily data with dates at midnight US Eastern time
    - Sometimes timezone-aware (America/New_York), sometimes naive
    - We need consistent UTC timestamps for database storage

    Args:
        df: DataFrame with DatetimeIndex

    Returns:
        DataFrame with UTC-normalized DatetimeIndex
    """
    if df.index.tz is None:
        # Naive datetime from yfinance is US Eastern midnight
        # First localize to US Eastern, then convert to UTC
        df.index = df.index.tz_localize(US_EASTERN).tz_convert(UTC)
    else:
        # Already timezone-aware, just convert to UTC
        df.index = df.index.tz_convert(UTC)

    # Remove timezone info for consistency with database (stores as TEXT)
    df.index = df.index.tz_localize(None)

    return df
```

- [ ] **Step 3: 测试时区标准化函数**

Run: `uv run python -c "import pandas as pd; from app.services.stock_updater import normalize_timezone; df = pd.DataFrame({'close': [100]}, index=pd.DatetimeIndex(['2026-03-24'])); result = normalize_timezone(df); print(f'Index: {result.index[0]}, TZ: {result.index.tz}')"`
Expected: 输出 UTC 时间且 TZ 为 None

- [ ] **Step 4: Commit**

```bash
git add app/services/stock_updater.py
git commit -m "feat: add timezone normalization for yfinance data

- Handle both naive and timezone-aware DatetimeIndex
- Convert US Eastern midnight to UTC
- Remove timezone info for database storage"
```

---

## Task 4: 创建数据更新模块（第2部分：数据拉取）

**Files:**
- Modify: `app/services/stock_updater.py`

- [ ] **Step 1: 实现数据拉取函数**

在 `app/services/stock_updater.py` 中添加：

```python
def fetch_recent_ohlc(symbols: List[str], days: int = 5) -> Dict[str, List[Dict]]:
    """
    Fetch recent OHLC data for multiple symbols using yfinance.

    Args:
        symbols: List of stock symbols
        days: Number of days to fetch (default: 5)

    Returns:
        Dict mapping symbol to list of OHLC records
    """
    logger.info(f"Fetching {days}-day data for {len(symbols)} symbols...")

    try:
        # Download data for all symbols at once
        data = yf.download(
            tickers=symbols,
            period=f'{days}d',
            interval='1d',
            group_by='ticker',
            auto_adjust=True,  # Use adjusted prices
            progress=False
        )

        result = {}

        for symbol in symbols:
            try:
                # Extract data for this symbol
                if len(symbols) == 1:
                    df = data
                else:
                    df = data[symbol]

                # Skip if no data
                if df.empty:
                    logger.warning(f"No data returned for {symbol}")
                    continue

                # Normalize timezone to UTC
                df = normalize_timezone(df)

                # Convert to list of dicts
                records = []
                for date, row in df.iterrows():
                    # Skip rows with NaN values
                    if pd.isna(row['Close']) or pd.isna(row['Open']):
                        continue

                    records.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': float(row['Close']),
                        'volume': int(row['Volume'])
                    })

                result[symbol] = records

                # Log with latest close price for visibility
                if records:
                    latest = records[-1]
                    logger.info(
                        f"✓ {symbol}: {len(records)} records | "
                        f"Latest: {latest['date']} Close=${latest['close']:.2f}"
                    )

            except Exception as e:
                logger.error(f"Failed to process {symbol}: {e}")
                continue

        return result

    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        return {}
```

- [ ] **Step 2: 测试数据拉取函数**

Run: `uv run python -c "from app.services.stock_updater import fetch_recent_ohlc; data = fetch_recent_ohlc(['AAPL'], days=2); print(f'AAPL records: {len(data.get(\"AAPL\", []))}')"`
Expected: 输出 "AAPL records: 2" 或类似数字，并显示日志

- [ ] **Step 3: Commit**

```bash
git add app/services/stock_updater.py
git commit -m "feat: add batch OHLC data fetching from yfinance

- Fetch multiple symbols in one API call
- Normalize timezone to UTC
- Skip rows with NaN values
- Log latest close price for each symbol"
```

---

## Task 5: 创建数据更新模块（第3部分：Upsert 逻辑）

**Files:**
- Modify: `app/services/stock_updater.py`

- [ ] **Step 1: 实现 Upsert 覆盖函数**

在 `app/services/stock_updater.py` 中添加：

```python
def upsert_ohlc_overwrite(symbol: str, data: List[Dict]):
    """
    Insert or UPDATE OHLC data (overwrites existing records).

    This is different from the original upsert_ohlc which uses DO NOTHING.
    We need DO UPDATE to support intraday updates of unclosed candles.

    Args:
        symbol: Stock symbol
        data: List of dicts with keys: date, open, high, low, close, volume
    """
    if not data:
        return

    from app.database.schema import get_conn

    conn = get_conn()

    # Use ON CONFLICT DO UPDATE to overwrite existing records
    conn.executemany("""
        INSERT INTO ohlc (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, date) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume
    """, [(symbol.upper(), d['date'], d['open'], d['high'], d['low'], d['close'], d['volume'])
          for d in data])

    conn.commit()
    conn.close()

    logger.debug(f"Upserted (overwrite) {len(data)} records for {symbol}")
```

- [ ] **Step 2: 测试 Upsert 函数**

Run: `uv run python -c "from app.services.stock_updater import upsert_ohlc_overwrite; test_data = [{'date': '2026-03-24', 'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.5, 'volume': 1000}]; upsert_ohlc_overwrite('TEST', test_data); print('Upsert successful')"`
Expected: 输出 "Upsert successful"

- [ ] **Step 3: 验证数据已写入**

Run: `uv run python -c "from app.database.ohlc import get_ohlc; records = get_ohlc('TEST', '2026-03-24', '2026-03-24'); print(f'Found {len(records)} records')"`
Expected: 输出 "Found 1 records"

- [ ] **Step 4: Commit**

```bash
git add app/services/stock_updater.py
git commit -m "feat: add upsert_ohlc_overwrite for intraday updates

- Use ON CONFLICT DO UPDATE instead of DO NOTHING
- Support overwriting unclosed candles during trading hours
- Maintain compatibility with existing database schema"
```

---

## Task 6: 创建数据更新模块（第4部分：同步更新函数）

**Files:**
- Modify: `app/services/stock_updater.py`

- [ ] **Step 1: 实现同步更新函数**

在 `app/services/stock_updater.py` 中添加：

```python
def update_stocks_intraday_sync():
    """
    Synchronous version of intraday stock update.
    
    This function contains blocking I/O (yfinance API + SQLite writes).
    Should be called via asyncio.to_thread() to avoid blocking event loop.
    """
    # Gatekeeper check
    if not should_update_stocks():
        return
    
    logger.info("=" * 60)
    logger.info("Starting intraday stock update")
    logger.info("=" * 60)
    
    # Fetch recent data (5 days for gap healing)
    data_by_symbol = fetch_recent_ohlc(SYMBOLS, days=5)
    
    if not data_by_symbol:
        logger.error("No data fetched, aborting update")
        return
    
    # Upsert data for each symbol
    success_count = 0
    today_prices = []  # For summary log
    
    for symbol, records in data_by_symbol.items():
        try:
            if records:
                # Use the new upsert function that overwrites
                upsert_ohlc_overwrite(symbol, records)
                
                # Update metadata
                dates = [r['date'] for r in records]
                update_metadata(symbol, min(dates), max(dates))
                
                # Collect today's price for summary
                latest = records[-1]
                today_prices.append(f"{symbol}=${latest['close']:.2f}")
                
                success_count += 1
            
        except Exception as e:
            logger.error(f"Failed to upsert {symbol}: {e}")
            continue
    
    # Summary log with today's prices
    logger.info("=" * 60)
    logger.info(f"Update complete: {success_count}/{len(SYMBOLS)} symbols updated")
    if today_prices:
        logger.info(f"Latest prices: {' | '.join(today_prices)}")
    logger.info("=" * 60)
```

- [ ] **Step 2: 测试同步更新函数（仅在交易时段）**

Run: `uv run python -c "from app.services.stock_updater import update_stocks_intraday_sync; update_stocks_intraday_sync()"`
Expected: 如果在交易时段，输出更新日志；否则输出 "Skipping update"

- [ ] **Step 3: Commit**

```bash
git add app/services/stock_updater.py
git commit -m "feat: add synchronous intraday update function

- Check gatekeeper before updating
- Fetch 5 days of data for gap healing
- Upsert with overwrite strategy
- Log summary with latest prices"
```

---

## Task 7: 创建数据更新模块（第5部分：异步包装器）

**Files:**
- Modify: `app/services/stock_updater.py`

- [ ] **Step 1: 实现异步包装器**

在 `app/services/stock_updater.py` 中添加：

```python
async def update_stocks_intraday():
    """
    Async wrapper for intraday stock update.
    
    Runs the synchronous update function in a thread pool to avoid
    blocking FastAPI's event loop.
    
    This is the function that should be called by APScheduler.
    """
    try:
        # Run blocking function in thread pool
        await asyncio.to_thread(update_stocks_intraday_sync)
    except Exception as e:
        logger.error(f"Intraday update failed: {e}", exc_info=True)
```

- [ ] **Step 2: 测试异步包装器**

Run: `uv run python -c "import asyncio; from app.services.stock_updater import update_stocks_intraday; asyncio.run(update_stocks_intraday())"`
Expected: 如果在交易时段，输出更新日志；否则输出 "Skipping update"

- [ ] **Step 3: Commit**

```bash
git add app/services/stock_updater.py
git commit -m "feat: add async wrapper for intraday update

- Use asyncio.to_thread() to avoid blocking event loop
- Catch and log all exceptions
- Ready for APScheduler integration"
```

---

## Task 8: 修改 FastAPI 主文件集成 APScheduler

**Files:**
- Modify: `app/api/main.py`

- [ ] **Step 1: 替换调度器导入语句**

在 `app/api/main.py` 中，找到第 13 行的导入语句：

```python
from apscheduler.schedulers.background import BackgroundScheduler
```

**替换**为：

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.stock_updater import update_stocks_intraday
```

- [ ] **Step 2: 替换全局调度器实例**

在 `app/api/main.py` 中，找到第 26 行的：

```python
scheduler = BackgroundScheduler()
```

**替换**为：

```python
# Create global scheduler instance (replaced BackgroundScheduler with AsyncIOScheduler)
scheduler = AsyncIOScheduler(timezone="America/New_York")
```

- [ ] **Step 3: 在 lifespan 函数中添加调度器配置**

在 `app/api/main.py` 的 `lifespan` 函数中，找到第 118-126 行（daily_ohlc_update 配置）：

```python
    # Update daily after US market close (UTC 21:30 = EST 16:30)
    scheduler.add_job(
        update_daily_ohlc,
        'cron',
        hour=21,
        minute=30,
        id='daily_ohlc_update'
    )
```

在这段代码**之后**、第 126 行 `scheduler.start()` **之前**添加：

```python
    # Add stock intraday update scheduler
    logger.info("Configuring intraday stock update scheduler...")

    scheduler.add_job(
        update_stocks_intraday,
        trigger=CronTrigger(
            minute='1,16,31,46',
            timezone='America/New_York'
        ),
        id='intraday_stock_update',
        name='Intraday Stock Data Update (15min)',
        replace_existing=True,
        max_instances=1
    )

    logger.info("✓ Intraday stock update configured: updates at :01, :16, :31, :46 (ET)")
```

注意：不要重复调用 `scheduler.start()`，它已经在第 126 行被调用。

- [ ] **Step 4: 验证 shutdown 逻辑已存在**

在 `app/api/main.py` 的 `lifespan` 函数中，确认第 138 行已有 `scheduler.shutdown()`。

无需修改，shutdown 逻辑已存在。此步骤仅验证。

- [ ] **Step 5: 验证修改**

Run: `uv run python -c "from app.api.main import app, scheduler; print(f'Scheduler type: {type(scheduler).__name__}')"`
Expected: 输出 "Scheduler type: AsyncIOScheduler"

- [ ] **Step 6: 启动应用测试（不要长时间运行）**

Run: `timeout 10 uv run uvicorn app.api.main:app --port 8080 || true`
Expected: 看到日志 "✓ APScheduler started: updates at :01, :16, :31, :46 (ET)"

- [ ] **Step 7: Commit**

```bash
git add app/api/main.py
git commit -m "feat: integrate APScheduler for intraday stock updates

- Use AsyncIOScheduler with America/New_York timezone
- Schedule updates at :01, :16, :31, :46 every hour
- Prevent overlapping executions with max_instances=1
- Graceful shutdown on application exit"
```

---

## Task 9: 创建并运行补数据脚本

**Files:**
- Create: `scripts/backfill_stock_gap.py`

- [ ] **Step 1: 创建补数据脚本**

创建 `scripts/backfill_stock_gap.py`，添加以下代码：

```python
"""
一次性补数据脚本，修复 2026-03-20 到 2026-03-23 的数据 Gap。

Usage:
    uv run python scripts/backfill_stock_gap.py
"""
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.stock_updater import (
    fetch_recent_ohlc,
    upsert_ohlc_overwrite,
    update_metadata,
    SYMBOLS
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 70)
    logger.info("开始补数据：2026-03-20 到 2026-03-23")
    logger.info("=" * 70)
    
    # 拉取最近 10 天数据（确保覆盖 Gap）
    logger.info("Fetching last 10 days of data to cover gap period...")
    data_by_symbol = fetch_recent_ohlc(SYMBOLS, days=10)
    
    if not data_by_symbol:
        logger.error("❌ 未获取到数据，终止补数据")
        return 1
    
    # Upsert 每只股票
    success_count = 0
    total_records = 0
    
    for symbol, records in data_by_symbol.items():
        try:
            if records:
                upsert_ohlc_overwrite(symbol, records)
                
                # Update metadata
                dates = [r['date'] for r in records]
                update_metadata(symbol, min(dates), max(dates))
                
                total_records += len(records)
                success_count += 1
                
                logger.info(f"✓ {symbol}: {len(records)} 条记录已补充")
            
        except Exception as e:
            logger.error(f"❌ {symbol} 补数据失败: {e}")
            continue
    
    logger.info("=" * 70)
    logger.info(f"补数据完成: {success_count}/{len(SYMBOLS)} 只股票")
    logger.info(f"Total records processed: {total_records}")
    logger.info("=" * 70)
    
    # 验证 Gap 已填补
    logger.info("\n验证 Gap 是否已填补...")
    from app.database.ohlc import get_ohlc
    
    for symbol in SYMBOLS:
        try:
            records = get_ohlc(symbol, '2026-03-20', '2026-03-23')
            logger.info(f"{symbol}: {len(records)} 条记录在 Gap 期间")
        except Exception as e:
            logger.error(f"Failed to verify {symbol}: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 运行补数据脚本**

Run: `uv run python scripts/backfill_stock_gap.py`
Expected: 输出补数据日志，显示每只股票的记录数

- [ ] **Step 3: 验证 Gap 已填补**

Run: `uv run python -c "from app.database.ohlc import get_ohlc; for symbol in ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']: records = get_ohlc(symbol, '2026-03-20', '2026-03-23'); print(f'{symbol}: {len(records)} records')"`
Expected: 每只股票显示 2 条记录（3/20 和 3/23）

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_stock_gap.py
git commit -m "feat: add backfill script for stock data gap

- Fetch last 10 days to cover 2026-03-20 to 2026-03-23 gap
- Use upsert_ohlc_overwrite to handle existing data
- Verify gap is filled after backfill"
```

---

## Task 10: 验证系统运行

**Files:**
- None (verification only)

- [ ] **Step 1: 启动应用**

Run: `uv run uvicorn app.api.main:app --port 8080`
Expected: 看到日志 "✓ APScheduler started: updates at :01, :16, :31, :46 (ET)"

- [ ] **Step 2: 检查调度器状态（在另一个终端）**

Run: `curl http://localhost:8080/api/scheduler/status 2>/dev/null | python -m json.tool`
Expected: 如果实现了监控端点，显示调度器状态；否则跳过此步骤

- [ ] **Step 3: 等待下一个触发时间**

等待到下一个 :01, :16, :31, 或 :46 分钟，观察日志输出。

Expected: 
- 如果在交易时段：看到 "Starting intraday stock update" 和更新日志
- 如果在盘外时段：看到 "Skipping update: outside trading hours"

- [ ] **Step 4: 验证数据已更新**

Run: `uv run python -c "from app.database.ohlc import get_ohlc; import datetime; today = datetime.date.today().isoformat(); records = get_ohlc('AAPL', today, today); print(f'AAPL today: {len(records)} records'); if records: print(f'Close: ${records[0][\"close\"]:.2f}')"`
Expected: 如果在交易日，显示今天的数据

- [ ] **Step 5: 检查日志文件（如果有）**

查看应用日志，确认：
- 守门员正常工作
- 数据拉取成功
- Upsert 成功
- 显示最新价格

- [ ] **Step 6: 最终验证 Commit**

```bash
git add -A
git commit -m "chore: verify intraday update system is working

- APScheduler triggers at correct times
- Gatekeeper correctly filters trading hours
- Data updates successfully
- Latest prices logged correctly"
```

---

## Success Criteria

✅ **依赖已安装**
- pandas-market-calendars 已安装并可导入

✅ **守门员正常工作**
- 交易时段返回 True
- 盘外时段返回 False
- 节假日返回 False

✅ **数据拉取正常**
- yfinance 成功拉取数据
- 时区正确转换为 UTC
- 数据格式正确（YYYY-MM-DD）

✅ **Upsert 逻辑正确**
- 新数据成功插入
- 已有数据成功覆盖
- 支持盘中多次更新

✅ **调度器正常运行**
- APScheduler 在正确时间触发
- 异步包装器不阻塞事件循环
- 应用启动和关闭正常

✅ **历史 Gap 已修复**
- 3/20 和 3/23 的数据已补充
- 所有 7 只股票数据完整

✅ **日志清晰可读**
- 显示守门员决策
- 显示每只股票的最新价格
- 显示更新成功/失败状态

---

## Rollback Plan

如果出现问题，可以回滚：

```bash
# 查看最近的提交
git log --oneline -10

# 回滚到实施前的状态
git reset --hard <commit-before-implementation>

# 或者逐个回滚提交
git revert <commit-hash>
```

---

## Notes

- 所有时间处理使用 UTC，避免时区问题
- 守门员使用美东时间判断交易时段
- 拉取 5 天数据实现自动 Gap 修复
- Upsert 覆盖策略支持盘中更新
- 异步包装器避免阻塞 FastAPI

