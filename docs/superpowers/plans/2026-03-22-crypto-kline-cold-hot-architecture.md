# 加密货币 K 线数据冷热分离架构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Lambda 架构变体的加密货币 K 线数据系统，通过冷热分离提供历史数据的准确性和实时数据的低延迟。

**Architecture:** 冷数据层使用 SQLite 存储 Binance Vision 历史数据，热数据层使用内存缓存（48小时）存储 Binance REST API 实时数据，聚合层在 FastAPI 中合并两者并去重返回。

**Tech Stack:** FastAPI, SQLite, pandas, httpx, APScheduler, pytest

---

## File Structure

### New Files

**Services Layer:**
- `app/services/__init__.py` - Services module initialization, export HOT_CACHE
- `app/services/hot_cache.py` - Hot cache global state and utilities
- `app/services/binance_client.py` - Binance REST API client
- `app/services/realtime_agent.py` - Real-time data warmup and update loop
- `app/services/batch_downloader.py` - Daily Binance Vision downloader

**API Layer:**
- `app/api/routes/crypto_klines.py` - New endpoint for cold-hot merged K-line data

**Tests:**
- `tests/services/test_hot_cache.py` - Hot cache unit tests
- `tests/services/test_binance_client.py` - Binance client unit tests
- `tests/services/test_realtime_agent.py` - Realtime agent unit tests
- `tests/services/test_batch_downloader.py` - Batch downloader unit tests
- `tests/api/test_crypto_klines.py` - API integration tests

### Modified Files

- `app/api/main.py` - Add lifespan context manager for hot cache warmup
- `app/database/crypto_ohlc.py` - Add batch upsert function (if not exists)
- `pyproject.toml` or `requirements.txt` - Add httpx, apscheduler dependencies

---
## Task 1: 热缓存基础设施

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/hot_cache.py`
- Create: `tests/services/test_hot_cache.py`

- [ ] **Step 1: Write failing test for hot cache initialization**

```python
# tests/services/test_hot_cache.py
import pytest
import pandas as pd
from app.services.hot_cache import HOT_CACHE, get_hot_cache, append_to_hot_cache, cleanup_hot_cache, get_cache_size

def test_hot_cache_initialization():
    """测试热缓存初始化结构"""
    assert "BTCUSDT" in HOT_CACHE
    assert "ETHUSDT" in HOT_CACHE
    assert isinstance(HOT_CACHE["BTCUSDT"], dict)
    assert isinstance(HOT_CACHE["ETHUSDT"], dict)

def test_get_hot_cache_empty():
    """测试获取空缓存"""
    df = get_hot_cache("BTCUSDT", "1m")
    assert df.empty
    assert list(df.columns) == ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/services/test_hot_cache.py::test_hot_cache_initialization -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.services'"

- [ ] **Step 3: Create services module and hot cache**

```python
# app/services/__init__.py
"""Services module for business logic."""
from .hot_cache import HOT_CACHE

__all__ = ["HOT_CACHE"]
```

```python
# app/services/hot_cache.py
"""Hot cache for real-time cryptocurrency K-line data."""
from typing import Dict, Optional
from datetime import datetime, timezone
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Global hot cache: {symbol: {interval: DataFrame}}
# Keeps last 48 hours of data (yesterday + today)
HOT_CACHE: Dict[str, Dict[str, pd.DataFrame]] = {
    "BTCUSDT": {},
    "ETHUSDT": {}
}

# DataFrame columns structure
CACHE_COLUMNS = ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']


def get_hot_cache(symbol: str, interval: str) -> pd.DataFrame:
    """Get hot cache DataFrame for symbol and interval.
    
    Returns empty DataFrame with correct columns if not found.
    """
    if symbol not in HOT_CACHE:
        return pd.DataFrame(columns=CACHE_COLUMNS)
    
    if interval not in HOT_CACHE[symbol]:
        return pd.DataFrame(columns=CACHE_COLUMNS)
    
    return HOT_CACHE[symbol][interval].copy()


def append_to_hot_cache(symbol: str, interval: str, new_data: list) -> None:
    """Append new data to hot cache with deduplication.
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Time interval (e.g., '1m', '15m', '1h')
        new_data: List of dicts with keys: timestamp, date, open, high, low, close, volume
    """
    if not new_data:
        return
    
    # Initialize if not exists
    if symbol not in HOT_CACHE:
        HOT_CACHE[symbol] = {}
    
    new_df = pd.DataFrame(new_data)
    
    if interval not in HOT_CACHE[symbol]:
        HOT_CACHE[symbol][interval] = new_df
        logger.debug(f"Initialized cache for {symbol} {interval}: {len(new_df)} records")
        return
    
    # Merge and deduplicate
    existing_df = HOT_CACHE[symbol][interval]
    combined = pd.concat([existing_df, new_df])
    combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
    combined = combined.sort_values('timestamp')
    
    # Limit cache size (max 2880 records = 48 hours × 60 minutes)
    if len(combined) > 2880:
        combined = combined.tail(2880)
        logger.debug(f"Trimmed cache for {symbol} {interval} to 2880 records")
    
    HOT_CACHE[symbol][interval] = combined
    logger.debug(f"Updated cache for {symbol} {interval}: {len(combined)} records")


def cleanup_hot_cache(symbol: str, interval: str, cutoff_date: datetime) -> None:
    """Remove data before cutoff date from hot cache.
    
    Args:
        symbol: Trading pair symbol
        interval: Time interval
        cutoff_date: Remove data before this datetime (UTC)
    """
    if symbol not in HOT_CACHE or interval not in HOT_CACHE[symbol]:
        return
    
    df = HOT_CACHE[symbol][interval]
    
    # Convert cutoff to timestamp for comparison
    cutoff_ts = int(cutoff_date.timestamp() * 1000)
    
    # Filter data >= cutoff
    filtered = df[df['timestamp'] >= cutoff_ts]
    
    removed_count = len(df) - len(filtered)
    if removed_count > 0:
        HOT_CACHE[symbol][interval] = filtered
        logger.info(f"Cleaned up {symbol} {interval}: removed {removed_count} records before {cutoff_date}")


def get_cache_size() -> int:
    """Calculate total hot cache size in bytes."""
    total_size = 0
    for symbol in HOT_CACHE:
        for interval in HOT_CACHE[symbol]:
            df = HOT_CACHE[symbol][interval]
            total_size += df.memory_usage(deep=True).sum()
    return total_size
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_hot_cache.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Add more tests for append and cleanup**

```python
# tests/services/test_hot_cache.py (append to file)

def test_append_to_hot_cache():
    """测试追加数据到热缓存"""
    from app.services.hot_cache import HOT_CACHE
    
    # Clear cache first
    HOT_CACHE["BTCUSDT"]["1m"] = pd.DataFrame()
    
    data = [
        {"timestamp": 1000, "date": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0}
    ]
    
    append_to_hot_cache("BTCUSDT", "1m", data)
    
    df = get_hot_cache("BTCUSDT", "1m")
    assert len(df) == 1
    assert df.iloc[0]['timestamp'] == 1000
    assert df.iloc[0]['close'] == 100.5


def test_append_deduplication():
    """测试追加时去重（保留最新）"""
    from app.services.hot_cache import HOT_CACHE
    
    HOT_CACHE["BTCUSDT"]["1m"] = pd.DataFrame()
    
    # First append
    data1 = [{"timestamp": 1000, "date": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0}]
    append_to_hot_cache("BTCUSDT", "1m", data1)
    
    # Second append with same timestamp but different close
    data2 = [{"timestamp": 1000, "date": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 102.0, "volume": 1000.0}]
    append_to_hot_cache("BTCUSDT", "1m", data2)
    
    df = get_hot_cache("BTCUSDT", "1m")
    assert len(df) == 1
    assert df.iloc[0]['close'] == 102.0  # Should keep last


def test_cleanup_hot_cache():
    """测试清理旧数据"""
    from app.services.hot_cache import HOT_CACHE
    from datetime import datetime, timezone
    
    HOT_CACHE["BTCUSDT"]["1m"] = pd.DataFrame([
        {"timestamp": 1000, "date": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
        {"timestamp": 2000, "date": "2024-01-01T00:01:00+00:00", "open": 100.5, "high": 101.5, "low": 99.5, "close": 101.0, "volume": 1100.0},
        {"timestamp": 3000, "date": "2024-01-01T00:02:00+00:00", "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1200.0}
    ])
    
    # Cleanup before timestamp 2000
    cutoff = datetime.fromtimestamp(2, tz=timezone.utc)  # timestamp 2000 ms = 2 seconds
    cleanup_hot_cache("BTCUSDT", "1m", cutoff)
    
    df = get_hot_cache("BTCUSDT", "1m")
    assert len(df) == 2  # Should keep 2000 and 3000
    assert df.iloc[0]['timestamp'] == 2000
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/services/test_hot_cache.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add app/services/__init__.py app/services/hot_cache.py tests/services/test_hot_cache.py
git commit -m "feat: add hot cache infrastructure for crypto K-line data"
```


## Task 2: Binance REST API 客户端

**Files:**
- Create: `app/services/binance_client.py`
- Create: `tests/services/test_binance_client.py`

- [ ] **Step 1: Write failing test for Binance client**

```python
# tests/services/test_binance_client.py
import pytest
from datetime import datetime, timezone
from app.services.binance_client import fetch_binance_klines, parse_kline_response

def test_parse_kline_response():
    """测试解析 Binance K 线响应"""
    raw_klines = [
        [1640995200000, "46000.00", "46500.00", "45800.00", "46200.00", "100.5", 1640998799999, "4620000.00", 1000, "50.2", "2310000.00", "0"]
    ]
    
    result = parse_kline_response(raw_klines)
    
    assert len(result) == 1
    assert result[0]['timestamp'] == 1640995200000
    assert result[0]['open'] == 46000.00
    assert result[0]['close'] == 46200.00
    assert result[0]['volume'] == 100.5
    assert '+00:00' in result[0]['date']  # UTC timezone

@pytest.mark.asyncio
async def test_fetch_binance_klines_basic():
    """测试基本的 K 线获取（需要网络）"""
    # This is an integration test - may be slow
    result = await fetch_binance_klines("BTCUSDT", "1d", limit=2)
    
    assert len(result) <= 2
    assert all('timestamp' in r for r in result)
    assert all('open' in r for r in result)
    assert all('close' in r for r in result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/services/test_binance_client.py::test_parse_kline_response -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.binance_client'"

- [ ] **Step 3: Implement Binance client**

```python
# app/services/binance_client.py
"""Binance REST API client for K-line data."""
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

BINANCE_API_BASE = "https://api.binance.com"
BINANCE_KLINES_ENDPOINT = "/api/v3/klines"


def parse_kline_response(klines: List[List]) -> List[Dict[str, Any]]:
    """Parse Binance K-line response into our format.
    
    Binance K-line format:
    [
        [
            1499040000000,      // Open time
            "0.01634000",       // Open
            "0.80000000",       // High
            "0.01575800",       // Low
            "0.01577100",       // Close
            "148976.11427815",  // Volume
            1499644799999,      // Close time
            "2434.19055334",    // Quote asset volume
            308,                // Number of trades
            "1756.87402397",    // Taker buy base asset volume
            "28.46694368",      // Taker buy quote asset volume
            "17928899.62484339" // Ignore
        ]
    ]
    
    Args:
        klines: Raw K-line data from Binance API
        
    Returns:
        List of dicts with keys: timestamp, date, open, high, low, close, volume
    """
    result = []
    
    for k in klines:
        timestamp_ms = int(k[0])
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        
        result.append({
            "timestamp": timestamp_ms,
            "date": dt.isoformat(),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5])
        })
    
    return result


async def fetch_binance_klines(
    symbol: str,
    interval: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """Fetch K-line data from Binance REST API.
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: K-line interval (1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M)
        start_time: Start time in milliseconds (optional)
        end_time: End time in milliseconds (optional)
        limit: Number of K-lines to fetch (default 500, max 1000)
        
    Returns:
        List of K-line dicts
        
    Raises:
        httpx.HTTPError: If API request fails
    """
    url = f"{BINANCE_API_BASE}{BINANCE_KLINES_ENDPOINT}"
    
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": min(limit, 1000)  # Binance max is 1000
    }
    
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        
        klines = response.json()
        return parse_kline_response(klines)


async def fetch_binance_klines_with_retry(
    symbol: str,
    interval: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 500,
    max_retries: int = 3
) -> List[Dict[str, Any]]:
    """Fetch K-line data with exponential backoff retry.
    
    Args:
        symbol: Trading pair symbol
        interval: K-line interval
        start_time: Start time in milliseconds (optional)
        end_time: End time in milliseconds (optional)
        limit: Number of K-lines to fetch
        max_retries: Maximum number of retry attempts
        
    Returns:
        List of K-line dicts
        
    Raises:
        httpx.HTTPError: If all retries fail
    """
    import asyncio
    
    for attempt in range(max_retries):
        try:
            return await fetch_binance_klines(symbol, interval, start_time, end_time, limit)
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to fetch {symbol} {interval} after {max_retries} attempts: {e}")
                raise
            
            wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
            logger.warning(f"Retry {attempt + 1}/{max_retries} for {symbol} {interval} after {wait_time}s")
            await asyncio.sleep(wait_time)
    
    return []  # Should never reach here
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_binance_client.py::test_parse_kline_response -v`
Expected: PASS

- [ ] **Step 5: Add mock test for fetch function**

```python
# tests/services/test_binance_client.py (append)

@pytest.mark.asyncio
async def test_fetch_binance_klines_mock(monkeypatch):
    """测试 K 线获取（使用 mock）"""
    from unittest.mock import AsyncMock, MagicMock
    
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.json.return_value = [
        [1640995200000, "46000.00", "46500.00", "45800.00", "46200.00", "100.5", 1640998799999, "4620000.00", 1000, "50.2", "2310000.00", "0"]
    ]
    mock_response.raise_for_status = MagicMock()
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get.return_value = mock_response
    
    # Patch httpx.AsyncClient
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda: mock_client)
    
    result = await fetch_binance_klines("BTCUSDT", "1d", limit=1)
    
    assert len(result) == 1
    assert result[0]['timestamp'] == 1640995200000
    assert result[0]['close'] == 46200.00
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/services/test_binance_client.py -v`
Expected: PASS (3 tests, 1 may be skipped if no network)

- [ ] **Step 7: Commit**

```bash
git add app/services/binance_client.py tests/services/test_binance_client.py
git commit -m "feat: add Binance REST API client for K-line data"
```


## Task 3: 实时代理 - 预热和更新循环

**Files:**
- Create: `app/services/realtime_agent.py`
- Create: `tests/services/test_realtime_agent.py`

- [ ] **Step 1: Write failing test for warmup function**

```python
# tests/services/test_realtime_agent.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from app.services.realtime_agent import warmup_hot_cache, update_hot_cache_once
from app.services.hot_cache import HOT_CACHE, get_hot_cache

@pytest.mark.asyncio
async def test_warmup_hot_cache():
    """测试热缓存预热"""
    # Mock fetch_binance_klines_with_retry
    mock_data = [
        {"timestamp": 1000, "date": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0}
    ]
    
    with patch('app.services.realtime_agent.fetch_binance_klines_with_retry', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_data
        
        # Clear cache
        HOT_CACHE["BTCUSDT"].clear()
        HOT_CACHE["ETHUSDT"].clear()
        
        await warmup_hot_cache()
        
        # Verify cache is populated
        assert "1m" in HOT_CACHE["BTCUSDT"]
        assert "15m" in HOT_CACHE["BTCUSDT"]
        assert len(get_hot_cache("BTCUSDT", "1m")) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/services/test_realtime_agent.py::test_warmup_hot_cache -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement realtime agent**

```python
# app/services/realtime_agent.py
"""Real-time agent for hot cache warmup and updates."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List
import logging

from .binance_client import fetch_binance_klines_with_retry
from .hot_cache import append_to_hot_cache, get_cache_size

logger = logging.getLogger(__name__)

# Configuration
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1m", "15m", "1h", "4h", "1d"]
UPDATE_INTERVAL_SECONDS = 60


async def warmup_hot_cache() -> None:
    """Warmup hot cache on application startup.
    
    Fetches today's data (UTC 00:00 to now) for all symbols and intervals.
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_time_ms = int(today_start.timestamp() * 1000)
    
    logger.info("Starting hot cache warmup...")
    
    tasks = []
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            tasks.append(_warmup_single(symbol, interval, start_time_ms))
    
    # Run all warmup tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Log results
    success_count = sum(1 for r in results if not isinstance(r, Exception))
    total_count = len(results)
    
    cache_size_mb = get_cache_size() / 1024 / 1024
    logger.info(f"Hot cache warmup complete: {success_count}/{total_count} successful, cache size: {cache_size_mb:.2f} MB")


async def _warmup_single(symbol: str, interval: str, start_time_ms: int) -> None:
    """Warmup cache for a single symbol and interval."""
    try:
        # Fetch today's data (limit 1500 should cover 1 day of 1m data)
        data = await fetch_binance_klines_with_retry(
            symbol=symbol,
            interval=interval,
            start_time=start_time_ms,
            limit=1500
        )
        
        if data:
            append_to_hot_cache(symbol, interval, data)
            logger.info(f"✓ Warmed up {symbol} {interval}: {len(data)} records")
        else:
            logger.warning(f"✗ No data for {symbol} {interval}")
            
    except Exception as e:
        logger.error(f"Failed to warmup {symbol} {interval}: {e}")
        raise


async def update_hot_cache_once() -> None:
    """Update hot cache once - fetch latest K-lines for all symbols/intervals."""
    logger.debug("Updating hot cache...")
    
    tasks = []
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            tasks.append(_update_single(symbol, interval))
    
    # Run all update tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Log errors only
    errors = [r for r in results if isinstance(r, Exception)]
    if errors:
        logger.warning(f"Hot cache update completed with {len(errors)} errors")


async def _update_single(symbol: str, interval: str) -> None:
    """Update cache for a single symbol and interval."""
    try:
        # Fetch latest 10 K-lines to ensure we don't miss any
        data = await fetch_binance_klines_with_retry(
            symbol=symbol,
            interval=interval,
            limit=10
        )
        
        if data:
            append_to_hot_cache(symbol, interval, data)
            logger.debug(f"Updated {symbol} {interval}: {len(data)} records")
            
    except Exception as e:
        logger.error(f"Failed to update {symbol} {interval}: {e}")
        raise


async def update_hot_cache_loop() -> None:
    """Background loop to update hot cache every 60 seconds.
    
    This function runs indefinitely until cancelled.
    """
    logger.info(f"Starting hot cache update loop (interval: {UPDATE_INTERVAL_SECONDS}s)")
    
    while True:
        try:
            await asyncio.sleep(UPDATE_INTERVAL_SECONDS)
            await update_hot_cache_once()
            
        except asyncio.CancelledError:
            logger.info("Hot cache update loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in hot cache update loop: {e}")
            # Continue loop even on error
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_realtime_agent.py::test_warmup_hot_cache -v`
Expected: PASS

- [ ] **Step 5: Add test for update function**

```python
# tests/services/test_realtime_agent.py (append)

@pytest.mark.asyncio
async def test_update_hot_cache_once():
    """测试单次更新热缓存"""
    mock_data = [
        {"timestamp": 2000, "date": "2024-01-01T00:01:00+00:00", "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1100.0}
    ]
    
    with patch('app.services.realtime_agent.fetch_binance_klines_with_retry', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_data
        
        # Pre-populate cache
        HOT_CACHE["BTCUSDT"]["1m"] = pd.DataFrame([
            {"timestamp": 1000, "date": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0}
        ])
        
        await update_hot_cache_once()
        
        # Verify new data is appended
        df = get_hot_cache("BTCUSDT", "1m")
        assert len(df) == 2
        assert df.iloc[1]['timestamp'] == 2000
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/services/test_realtime_agent.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add app/services/realtime_agent.py tests/services/test_realtime_agent.py
git commit -m "feat: add realtime agent for hot cache warmup and updates"
```


## Task 4: 批量下载器 - Binance Vision 日线包

**Files:**
- Create: `app/services/batch_downloader.py`
- Create: `tests/services/test_batch_downloader.py`

- [ ] **Step 1: Write failing test for download function**

```python
# tests/services/test_batch_downloader.py
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.batch_downloader import download_binance_daily, daily_download_task

@pytest.mark.asyncio
async def test_download_binance_daily_success():
    """测试成功下载 Binance Vision 日线包"""
    import io
    import zipfile
    
    # Create mock ZIP file
    csv_content = b"1640995200000,46000.00,46500.00,45800.00,46200.00,100.5,1640998799999,4620000.00,1000,50.2,2310000.00,0\n"
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr("BTCUSDT-1h-2024-01-01.csv", csv_content)
    zip_buffer.seek(0)
    
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = zip_buffer.read()
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        with patch('app.services.batch_downloader.upsert_crypto_ohlc_batch') as mock_upsert:
            success = await download_binance_daily("BTCUSDT", "1h", date(2024, 1, 1))
            
            assert success is True
            assert mock_upsert.called

@pytest.mark.asyncio
async def test_download_binance_daily_not_found():
    """测试文件不存在（404）"""
    mock_response = MagicMock()
    mock_response.status_code = 404
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        success = await download_binance_daily("BTCUSDT", "1h", date(2099, 1, 1))
        
        assert success is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/services/test_batch_downloader.py::test_download_binance_daily_success -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement batch downloader**

```python
# app/services/batch_downloader.py
"""Batch downloader for Binance Vision historical data."""
import asyncio
import httpx
import zipfile
import io
from datetime import datetime, timezone, timedelta, date
from typing import Optional
import pandas as pd
import logging

from app.database.crypto_ohlc import upsert_crypto_ohlc
from .hot_cache import cleanup_hot_cache

logger = logging.getLogger(__name__)

BINANCE_VISION_BASE_URL = "https://data.binance.vision/data/spot/daily/klines"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1m", "15m", "1h", "4h", "1d"]

# Binance K-line CSV columns (no header)
BINANCE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
]


async def download_binance_daily(symbol: str, interval: str, target_date: date) -> bool:
    """Download single daily K-line package from Binance Vision.
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: K-line interval (e.g., '1m', '1h', '1d')
        target_date: Date to download
        
    Returns:
        True if successful, False if file not found or error
    """
    # Construct URL
    date_str = target_date.strftime("%Y-%m-%d")
    filename = f"{symbol}-{interval}-{date_str}.zip"
    url = f"{BINANCE_VISION_BASE_URL}/{symbol}/{interval}/{filename}"
    
    logger.info(f"Downloading {filename}...")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            
            if response.status_code == 404:
                logger.warning(f"File not found: {filename}")
                return False
            
            response.raise_for_status()
        
        # Extract and parse CSV
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                df = pd.read_csv(f, names=BINANCE_COLUMNS)
        
        # Convert timestamps and format
        df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
        df['date'] = df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        
        # Convert to database format
        db_symbol = f"{symbol[:3]}-{symbol[3:]}"  # BTCUSDT -> BTC-USDT
        records = []
        
        for _, row in df.iterrows():
            timestamp_ms = int(row['open_time'])
            records.append({
                "timestamp": timestamp_ms,
                "date": row['date'],
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": float(row['volume'])
            })
        
        # Batch insert to database
        count = upsert_crypto_ohlc(db_symbol, interval, records)
        logger.info(f"✓ Downloaded {filename}: {count} records inserted")
        
        return True
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error downloading {filename}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error processing {filename}: {e}")
        return False


async def daily_download_task() -> None:
    """Daily task to download yesterday's data from Binance Vision.
    
    Should be scheduled to run at UTC 08:00 or later.
    """
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    
    logger.info(f"Starting daily download task for {yesterday}")
    
    success_count = 0
    total_count = len(SYMBOLS) * len(INTERVALS)
    
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            try:
                success = await download_binance_daily(symbol, interval, yesterday)
                
                if success:
                    success_count += 1
                    
                    # Cleanup hot cache for this symbol/interval
                    # Remove data before today UTC 00:00
                    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    cleanup_hot_cache(symbol, interval, today_start)
                    logger.info(f"Cleaned up hot cache for {symbol} {interval}")
                else:
                    logger.warning(f"Failed to download {symbol} {interval} for {yesterday}")
                    
            except Exception as e:
                logger.error(f"Error processing {symbol} {interval}: {e}")
                continue
    
    logger.info(f"Daily download task complete: {success_count}/{total_count} successful")


async def download_with_retry(max_attempts: int = 24) -> None:
    """Download with hourly retry until successful.
    
    Args:
        max_attempts: Maximum retry attempts (default 24 hours)
    """
    for attempt in range(max_attempts):
        try:
            await daily_download_task()
            logger.info("Daily download successful")
            return
        except Exception as e:
            logger.error(f"Daily download attempt {attempt + 1} failed: {e}")
            
            if attempt < max_attempts - 1:
                logger.info(f"Retrying in 1 hour...")
                await asyncio.sleep(3600)  # 1 hour
    
    logger.error(f"Daily download failed after {max_attempts} attempts")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_batch_downloader.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/batch_downloader.py tests/services/test_batch_downloader.py
git commit -m "feat: add batch downloader for Binance Vision daily packages"
```


## Task 5: API 聚合层 - 冷热数据合并

**Files:**
- Create: `app/api/routes/crypto_klines.py`
- Create: `tests/api/test_crypto_klines.py`
- Modify: `app/api/main.py` (add router)

- [ ] **Step 1: Write failing test for API endpoint**

```python
# tests/api/test_crypto_klines.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import pandas as pd

from app.api.main import app

client = TestClient(app)

def test_get_crypto_klines_success():
    """测试成功获取 K 线数据"""
    # Mock cold data from database
    mock_cold_data = [
        {"timestamp": 1000, "date": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0}
    ]
    
    # Mock hot data from cache
    mock_hot_df = pd.DataFrame([
        {"timestamp": 2000, "date": "2024-01-01T00:01:00+00:00", "open": 100.5, "high": 101.5, "low": 99.5, "close": 101.0, "volume": 1100.0}
    ])
    
    with patch('app.api.routes.crypto_klines.get_crypto_ohlc', return_value=mock_cold_data):
        with patch('app.api.routes.crypto_klines.get_hot_cache', return_value=mock_hot_df):
            response = client.get("/api/crypto/klines?symbol=BTCUSDT&interval=1m&start=2024-01-01T00:00:00&end=2024-01-01T23:59:59")
            
            assert response.status_code == 200
            data = response.json()
            assert data['symbol'] == 'BTCUSDT'
            assert data['interval'] == '1m'
            assert len(data['data']) == 2  # Cold + hot merged

def test_get_crypto_klines_invalid_interval():
    """测试无效的时间间隔"""
    response = client.get("/api/crypto/klines?symbol=BTCUSDT&interval=invalid&start=2024-01-01&end=2024-01-02")
    
    assert response.status_code == 400
    assert "Invalid interval" in response.json()['detail']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_crypto_klines.py::test_get_crypto_klines_success -v`
Expected: FAIL with "404 Not Found" (route doesn't exist yet)

- [ ] **Step 3: Implement API endpoint**

```python
# app/api/routes/crypto_klines.py
"""API endpoints for crypto K-line data with cold-hot merge."""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
import pandas as pd
import logging

from app.database.crypto_ohlc import get_crypto_ohlc
from app.services.hot_cache import get_hot_cache

logger = logging.getLogger(__name__)
router = APIRouter()

# Interval mapping: API format -> Database format
INTERVAL_MAP = {
    "1m": "1m",
    "15m": "15m",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D"
}


@router.get("/api/crypto/klines")
async def get_crypto_klines(
    symbol: str = Query(..., description="Trading pair symbol (e.g., BTCUSDT)"),
    interval: str = Query(..., description="Time interval (1m, 15m, 1h, 4h, 1d)"),
    start: str = Query(..., description="Start time (ISO format)"),
    end: str = Query(..., description="End time (ISO format)")
) -> Dict[str, Any]:
    """Get crypto K-line data with automatic cold-hot merge.
    
    Merges historical data from SQLite with real-time data from hot cache.
    Deduplicates by timestamp, keeping hot data when conflicts occur.
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Time interval (1m, 15m, 1h, 4h, 1d)
        start: Start time in ISO format
        end: End time in ISO format
        
    Returns:
        JSON with symbol, interval, and merged data array
        
    Raises:
        HTTPException: 400 for invalid interval, 404 if no data found
    """
    # Validate interval
    bar = INTERVAL_MAP.get(interval)
    if not bar:
        valid_intervals = list(INTERVAL_MAP.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval: {interval}. Must be one of: {', '.join(valid_intervals)}"
        )
    
    # Convert symbol format for database (BTCUSDT -> BTC-USDT)
    db_symbol = f"{symbol[:3]}-{symbol[3:]}"
    
    try:
        # 1. Query cold data from SQLite
        cold_data = get_crypto_ohlc(db_symbol, bar, start, end)
        logger.debug(f"Cold data: {len(cold_data)} records")
        
        # 2. Query hot data from cache
        hot_df = get_hot_cache(symbol, interval)
        
        if not hot_df.empty:
            # Filter by date range
            hot_data_filtered = hot_df[
                (hot_df['date'] >= start) & 
                (hot_df['date'] <= end)
            ]
            logger.debug(f"Hot data: {len(hot_data_filtered)} records")
        else:
            hot_data_filtered = pd.DataFrame()
        
        # 3. Merge and deduplicate
        combined = pd.concat([
            pd.DataFrame(cold_data),
            hot_data_filtered
        ])
        
        if combined.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {symbol} {interval} between {start} and {end}"
            )
        
        # Deduplicate: keep='last' means hot data wins
        combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
        combined = combined.sort_values('timestamp')
        
        # 4. Return result
        result_data = combined[['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']].to_dict('records')
        
        logger.info(f"Returned {len(result_data)} records for {symbol} {interval}")
        
        return {
            "symbol": symbol,
            "interval": interval,
            "data": result_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching K-line data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
```

- [ ] **Step 4: Add router to main.py**

```python
# app/api/main.py (modify imports and router registration)
# Add to imports:
from .routes import analyze, reports, system, settings, stocks, ohlc, history, okx, crypto, crypto_klines

# Add after other router registrations:
app.include_router(crypto_klines.router, tags=["crypto-klines"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_crypto_klines.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Test deduplication logic**

```python
# tests/api/test_crypto_klines.py (append)

def test_get_crypto_klines_deduplication():
    """测试冷热数据去重（热数据优先）"""
    # Both cold and hot have timestamp 1000, hot should win
    mock_cold_data = [
        {"timestamp": 1000, "date": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0}
    ]
    
    mock_hot_df = pd.DataFrame([
        {"timestamp": 1000, "date": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 102.0, "volume": 1000.0}
    ])
    
    with patch('app.api.routes.crypto_klines.get_crypto_ohlc', return_value=mock_cold_data):
        with patch('app.api.routes.crypto_klines.get_hot_cache', return_value=mock_hot_df):
            response = client.get("/api/crypto/klines?symbol=BTCUSDT&interval=1m&start=2024-01-01&end=2024-01-02")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data['data']) == 1  # Deduplicated
            assert data['data'][0]['close'] == 102.0  # Hot data wins
```

- [ ] **Step 7: Run all tests**

Run: `uv run pytest tests/api/test_crypto_klines.py -v`
Expected: PASS (3 tests)

- [ ] **Step 8: Commit**

```bash
git add app/api/routes/crypto_klines.py app/api/main.py tests/api/test_crypto_klines.py
git commit -m "feat: add API endpoint for cold-hot merged crypto K-line data"
```


## Task 6: FastAPI 生命周期集成

**Files:**
- Modify: `app/api/main.py`

- [ ] **Step 1: Add lifespan context manager**

```python
# app/api/main.py (add after imports)
from contextlib import asynccontextmanager
import asyncio

from app.services.realtime_agent import warmup_hot_cache, update_hot_cache_loop
from app.services.batch_downloader import daily_download_task

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown tasks."""
    # Startup
    logger.info("Starting application...")
    
    # Initialize agent history database (existing)
    db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")
    init_agent_history_db(db_path)
    logger.info(f"✓ Agent history database initialized: {db_path}")
    
    # Warmup hot cache
    await warmup_hot_cache()
    logger.info("✓ Hot cache warmed up")
    
    # Start hot cache update loop
    update_task = asyncio.create_task(update_hot_cache_loop())
    logger.info("✓ Hot cache update loop started")
    
    # Start scheduler for daily tasks (existing + new)
    scheduler.add_job(
        update_daily_ohlc,
        'cron',
        hour=21,
        minute=30,
        id='daily_ohlc_update'
    )
    
    # Add daily Binance Vision download task (UTC 08:00)
    scheduler.add_job(
        lambda: asyncio.create_task(daily_download_task()),
        'cron',
        hour=8,
        minute=0,
        timezone='UTC',
        id='daily_binance_download'
    )
    
    scheduler.start()
    logger.info("✓ Scheduler started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    update_task.cancel()
    try:
        await update_task
    except asyncio.CancelledError:
        pass
    
    scheduler.shutdown()
    logger.info("✓ Application shutdown complete")
```

- [ ] **Step 2: Update FastAPI app initialization**

```python
# app/api/main.py (modify app creation)
app = FastAPI(
    title="Finance Agent API",
    description="Multi-agent financial analysis system API",
    version="0.1.0",
    lifespan=lifespan  # Add lifespan parameter
)
```

- [ ] **Step 3: Remove old startup/shutdown handlers**

```python
# app/api/main.py (remove these functions)
# DELETE:
# @app.on_event("startup")
# def start_scheduler():
#     ...
#
# @app.on_event("shutdown")
# def shutdown_scheduler():
#     ...
```

- [ ] **Step 4: Test application startup**

Run: `uv run uvicorn app.api.main:app --workers 1 --port 8000`
Expected: Application starts, logs show:
- "✓ Hot cache warmed up"
- "✓ Hot cache update loop started"
- "✓ Scheduler started"

Stop with Ctrl+C, verify graceful shutdown.

- [ ] **Step 5: Test API endpoint**

Start app: `uv run uvicorn app.api.main:app --workers 1 --port 8000`

Test: `curl "http://localhost:8000/api/crypto/klines?symbol=BTCUSDT&interval=1d&start=2024-01-01&end=2024-01-31"`

Expected: JSON response with K-line data

- [ ] **Step 6: Commit**

```bash
git add app/api/main.py
git commit -m "feat: integrate hot cache and batch downloader into FastAPI lifecycle"
```

---

## Task 7: 添加依赖和文档

**Files:**
- Modify: `pyproject.toml` or `requirements.txt`
- Create: `docs/crypto-kline-architecture.md`

- [ ] **Step 1: Add dependencies**

If using `pyproject.toml`:
```toml
[project.dependencies]
httpx = "^0.27.0"
apscheduler = "^3.10.4"
```

If using `requirements.txt`:
```
httpx>=0.27.0
apscheduler>=3.10.4
```

- [ ] **Step 2: Install dependencies**

Run: `uv pip install httpx apscheduler`
Expected: Dependencies installed successfully

- [ ] **Step 3: Create architecture documentation**

```markdown
# docs/crypto-kline-architecture.md
# 加密货币 K 线数据冷热分离架构

## 概述

本系统采用 Lambda 架构变体，实现历史数据与实时数据的分离存储和查询。

## 架构图

```
Binance Vision (历史) → SQLite (冷数据)
                                    ↘
                                     API 响应
                                    ↗
Binance REST API (实时) → 内存缓存 (热数据)
```

## 组件说明

### 冷数据层
- **存储**: SQLite `crypto_ohlc` 表
- **数据源**: Binance Vision 官方归档
- **更新**: 每天 UTC 08:00

### 热数据层
- **存储**: Python 进程内存（48 小时）
- **数据源**: Binance REST API
- **更新**: 每 60 秒

### API 层
- **端点**: `/api/crypto/klines`
- **功能**: 自动合并冷热数据并去重

## 使用说明

### 启动应用

```bash
uv run uvicorn app.api.main:app --workers 1 --port 8000
```

**注意**: 必须使用 `--workers 1`（单进程）

### 查询 K 线数据

```bash
curl "http://localhost:8000/api/crypto/klines?symbol=BTCUSDT&interval=1h&start=2024-01-01T00:00:00&end=2024-01-31T23:59:59"
```

支持的时间间隔: `1m`, `15m`, `1h`, `4h`, `1d`

## 监控

查看日志以监控系统状态:
- 热缓存大小
- 更新延迟
- 下载任务状态

## 故障排查

### 热缓存未预热
检查启动日志，确认 "✓ Hot cache warmed up" 出现

### API 返回 404
检查数据库是否有历史数据，热缓存是否有当天数据

### 定时任务未执行
检查 APScheduler 日志，确认任务已注册
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/services/ tests/api/test_crypto_klines.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml docs/crypto-kline-architecture.md
git commit -m "docs: add dependencies and architecture documentation"
```

---

## Execution Options

Plan complete and saved to `docs/superpowers/plans/2026-03-22-crypto-kline-cold-hot-architecture.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
